from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock

# ====================== CONFIG ======================
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

# ====================== LOGGER ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ====================== APP ======================
app = Flask(__name__)

# ====================== SHOPIFY ======================
import requests
session = requests.Session()

def shopify_request(method, url, **kwargs):
    attempt = 0
    while True:
        time.sleep(0.7)
        try:
            r = session.request(method, url, **kwargs, timeout=30)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "8")
                wait = max(float(retry_after), 2)
                logger.warning(f"429 rate limit → attente {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt >= 8:
                logger.error(f"Erreur réseau après 8 tentatives: {e}")
                raise
            wait = 2 ** attempt
            logger.warning(f"Erreur réseau (tentative {attempt}/8) → attente {wait}s : {e}")
            time.sleep(wait)

def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    while url:
        r = shopify_request("GET", url, headers=headers)
        products.extend(r.json()["products"])
        url = None
        link = r.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")
                break
    return products

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    r = shopify_request("GET", url, headers={"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN})
    locations = r.json()["locations"]
    if locations:
        return locations[0]["id"]
    else:
        logger.error("❌ Aucune location Shopify trouvée")
        return None

def update_shopify_stock(inventory_item_id, location_id, stock):
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": stock}
    shopify_request("POST", url, json=payload, headers=headers)
    logger.info(f"✅ Stock mis à jour pour inventory_item_id={inventory_item_id} → {stock}")

# ====================== SYNC ======================
def sync_all_products():
    logger.info("🔄 Début synchronisation automatique")
    try:
        nova = get_novaengel_stock()
        if not nova:
            logger.error("❌ Impossible de récupérer le stock NovaEngel")
            return
            
        shopify = get_all_shopify_products()
        location_id = get_shopify_location_id()
        
        if not location_id:
            logger.error("❌ Impossible de récupérer la location Shopify")
            return

        # Créer un dictionnaire SKU → Stock
        nova_map = {}
        for item in nova:
            item_id = item.get("Id")
            if item_id:
                nova_map[str(item_id).strip()] = item.get("Stock", 0)
        
        logger.info(f"📊 {len(nova_map)} produits NovaEngel trouvés")
        modified = 0

        for product in shopify:
            for variant in product["variants"]:
                sku = str(variant.get("sku", "")).strip()
                if not sku:
                    continue
                    
                # Nettoyer le SKU
                sku_clean = sku.replace("'", "").replace('"', '').strip()
                
                if sku_clean in nova_map:
                    current_stock = variant.get("inventory_quantity", 0)
                    new_stock = nova_map[sku_clean]
                    
                    if current_stock != new_stock:
                        update_shopify_stock(variant["inventory_item_id"], location_id, new_stock)
                        logger.info(f"MISE À JOUR → {product['title']} | SKU {sku_clean} : {current_stock} → {new_stock}")
                        modified += 1
                else:
                    logger.debug(f"SKU non trouvé dans NovaEngel: {sku_clean}")

        logger.info(f"SYNCHRONISATION TERMINÉE → {modified} produit(s) mis à jour" if modified else "✅ Synchronisation OK - Aucune modification")
    except Exception as e:
        logger.exception(f"❌ Erreur lors de la synchronisation: {e}")

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="sync_job")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))

# ====================== ROUTES ======================
@app.route("/sync")
def manual_sync():
    """Route manuelle pour synchroniser"""
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync lancée"}), 200

@app.route("/")
def home():
    return """
    <h3>Sync NovaEngel → Shopify – AUTOMATIQUE TOUTES LES HEURES</h3>
    <p>Routes disponibles:</p>
    <ul>
        <li><a href="/test-novaengel">/test-novaengel</a> - Test d'envoi de commande</li>
        <li><a href="/health">/health</a> - Vérification santé</li>
        <li><a href="/sync?key=VOTRE_CLE">/sync?key=XXX</a> - Sync manuelle</li>
    </ul>
    """

@app.route("/health")
def health():
    """Route de santé pour vérifier que l'API fonctionne"""
    return jsonify({
        "status": "healthy",
        "service": "NovaEngel-Shopify Sync",
        "timestamp": time.time()
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("=== WEBHOOK SHOPIFY DÉCLENCHÉ ===")
    
    try:
        order = request.get_json(force=True)
        logger.info(f"📦 Commande reçue: {order.get('name', 'N/A')}")
        logger.info(f"📦 Email client: {order.get('email', 'N/A')}")
        logger.info(f"📦 Total: {order.get('total_price', 'N/A')}")
        
        # Lancer l'envoi dans un thread
        threading.Thread(target=send_order_to_novaengel, args=(order,)).start()
        
        return jsonify({"status": "order processing started", "order": order.get('name')}), 200
        
    except Exception as e:
        logger.exception("❌ Erreur webhook commande")
        return jsonify({"error": str(e)}), 500

@app.route("/test-novaengel", methods=["GET"])
def test_novaengel():
    """Route de test pour NovaEngel"""
    logger.info("=== TEST NOVAENGEL ===")
    
    # Créez un ordre de test réaliste
    test_order = {
        "name": f"TEST{int(time.time()) % 10000}",
        "email": "test@example.com",
        "total_price": "45.50",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "8410190613430",  # EAN du manuel
                "quantity": 1,
                "price": "25.75"
            },
            {
                "sku": "841819825448",   # EAN du manuel  
                "quantity": 2,
                "price": "9.88"
            }
        ],
        "shipping_address": {
            "first_name": "Jean",
            "last_name": "Dupont",
            "address1": "12 Rue de la Paix",
            "city": "Paris",
            "zip": "75002",
            "country": "France",
            "country_code": "FR",
            "province": "Île-de-France",
            "phone": "0612345678"
        }
    }
    
    logger.info(f"📦 Envoi commande test: {test_order['name']}")
    
    # Envoi direct (pas dans un thread pour voir les logs)
    send_order_to_novaengel(test_order)
    
    return jsonify({
        "status": "test envoyé",
        "order_number": test_order["name"],
        "message": "Vérifiez les logs pour le résultat"
    }), 200

# ====================== START ======================
if __name__ == "__main__":
    logger.info("🚀 Démarrage de l'application...")
    logger.info(f"🛍️  Store Shopify: {SHOPIFY_STORE}")
    
    # Démarrer la sync initiale après 5 secondes
    time.sleep(5)
    threading.Thread(target=sync_all_products).start()
    
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Serveur démarré sur le port {port}")
    app.run(host="0.0.0.0", port=port, threaded=True)