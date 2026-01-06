from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock, get_novaengel_token

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

def shopify_request(method, url, **kwargs):
    """Fonction wrapper pour les requêtes Shopify"""
    try:
        headers = kwargs.get('headers', {})
        if 'X-Shopify-Access-Token' not in headers:
            headers['X-Shopify-Access-Token'] = SHOPIFY_ACCESS_TOKEN
            kwargs['headers'] = headers
        
        r = requests.request(method, url, timeout=30, **kwargs)
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        logger.error(f"Erreur Shopify: {e}")
        raise

def get_all_shopify_products():
    """Récupère tous les produits Shopify"""
    try:
        products = []
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
        
        while url:
            r = shopify_request("GET", url)
            data = r.json()
            products.extend(data["products"])
            
            # Pagination
            link = r.headers.get("Link", "")
            url = None
            if 'rel="next"' in link:
                for part in link.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip("<> ")
                        break
        
        logger.info(f"📊 {len(products)} produits Shopify récupérés")
        return products
    except Exception as e:
        logger.error(f"Erreur récupération produits Shopify: {e}")
        return []

def get_shopify_location_id():
    """Récupère l'ID de la location Shopify"""
    try:
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
        r = shopify_request("GET", url)
        locations = r.json()["locations"]
        
        if locations:
            return locations[0]["id"]
        return None
    except:
        return None

def update_shopify_stock(inventory_item_id, location_id, stock):
    """Met à jour le stock Shopify"""
    try:
        url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": stock
        }
        shopify_request("POST", url, json=payload)
        return True
    except:
        return False

# ====================== SYNC STOCK ======================
def sync_all_products():
    """Synchronise le stock NovaEngel → Shopify"""
    logger.info("🔄 Synchronisation stock")
    
    try:
        # 1. Stock NovaEngel
        nova_stock = get_novaengel_stock()
        if not nova_stock:
            logger.error("❌ Pas de stock NovaEngel")
            return
        
        # 2. Produits Shopify
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()
        
        if not location_id:
            logger.error("❌ Pas de location Shopify")
            return
        
        # 3. Mapping
        nova_map = {}
        for item in nova_stock:
            item_id = item.get("Id")
            if item_id:
                nova_map[str(item_id).strip()] = item.get("Stock", 0)
        
        # 4. Mise à jour
        updated = 0
        for product in shopify_products:
            for variant in product["variants"]:
                sku = str(variant.get("sku", "")).strip()
                if sku in nova_map:
                    current = variant.get("inventory_quantity", 0)
                    new = nova_map[sku]
                    
                    if current != new:
                        if update_shopify_stock(variant["inventory_item_id"], location_id, new):
                            logger.info(f"📦 {product['title'][:20]}...: {current}→{new}")
                            updated += 1
        
        logger.info(f"✅ {updated} produits mis à jour")
    except Exception as e:
        logger.error(f"❌ Erreur sync: {e}")

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ====================== ROUTES ======================
@app.route("/")
def home():
    return """
    <h3>🔄 Sync NovaEngel → Shopify</h3>
    <p><a href="/test">/test</a> - Tester une commande</p>
    <p><a href="/sync-manual?key=pl0reals">/sync-manual</a> - Sync manuelle</p>
    <p><a href="/health">/health</a> - Santé</p>
    """

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": time.time()}), 200

@app.route("/sync-manual")
def sync_manual():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "Mauvaise clé"}), 403
    
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync démarrée"}), 200

@app.route("/test")
def test_route():
    """Test simple d'envoi de commande"""
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "total_price": "50.00",
        "line_items": [
            {"sku": "8436097094189", "quantity": 2, "price": "25.00"}
        ],
        "shipping_address": {
            "first_name": "Jean",
            "last_name": "Dupont",
            "address1": "1 Rue Test",
            "city": "Paris",
            "zip": "75001",
            "country": "France",
            "phone": "0612345678"
        }
    }
    
    success = send_order_to_novaengel(test_order)
    return jsonify({
        "status": "success" if success else "error",
        "order": test_order["name"]
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_webhook():
    """Webhook Shopify"""
    try:
        order = request.get_json(force=True)
        logger.info(f"🛒 Commande reçue: {order.get('name')}")
        
        # Envoyer dans un thread
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        return jsonify({"status": "processing"}), 200
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    logger.info("🚀 Démarrage...")
    
    # Sync initiale
    time.sleep(3)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)