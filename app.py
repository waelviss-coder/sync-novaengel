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
session = requests.Session()

def shopify_request(method, url, **kwargs):
    """Fonction wrapper pour les requêtes Shopify avec retry"""
    attempt = 0
    while True:
        time.sleep(0.7)  # Éviter rate limiting
        try:
            r = session.request(method, url, **kwargs, timeout=30)
            if r.status_code == 429:  # Rate limit
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
    """Récupère tous les produits Shopify"""
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    
    while url:
        r = shopify_request("GET", url, headers=headers)
        data = r.json()
        products.extend(data["products"])
        
        # Pagination
        url = None
        link = r.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")
                break
    
    logger.info(f"📊 {len(products)} produits Shopify récupérés")
    return products

def get_shopify_location_id():
    """Récupère l'ID de la location Shopify"""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    r = shopify_request("GET", url, headers={"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN})
    locations = r.json()["locations"]
    
    if locations:
        location_id = locations[0]["id"]
        logger.info(f"📍 Location Shopify ID: {location_id}")
        return location_id
    else:
        logger.error("❌ Aucune location Shopify trouvée")
        return None

def update_shopify_stock(inventory_item_id, location_id, stock):
    """Met à jour le stock Shopify"""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": stock
    }
    
    shopify_request("POST", url, json=payload, headers=headers)
    logger.info(f"✅ Stock mis à jour: {inventory_item_id} → {stock}")

# ====================== SYNC STOCK ======================
def sync_all_products():
    """Synchronise le stock NovaEngel → Shopify"""
    logger.info("🔄 Début synchronisation automatique")
    
    try:
        # 1. Récupérer stock NovaEngel
        nova_stock = get_novaengel_stock()
        if not nova_stock:
            logger.error("❌ Impossible de récupérer le stock NovaEngel")
            return
        
        # 2. Récupérer produits Shopify
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()
        
        if not location_id:
            logger.error("❌ Impossible de récupérer la location Shopify")
            return
        
        # 3. Créer mapping SKU → Stock
        nova_map = {}
        for item in nova_stock:
            item_id = item.get("Id")
            if item_id:
                nova_map[str(item_id).strip()] = item.get("Stock", 0)
        
        logger.info(f"📊 {len(nova_map)} produits NovaEngel chargés")
        
        # 4. Comparer et mettre à jour
        modified = 0
        for product in shopify_products:
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
                        update_shopify_stock(
                            variant["inventory_item_id"],
                            location_id,
                            new_stock
                        )
                        logger.info(f"📦 Mise à jour: {product['title'][:30]}... | SKU {sku_clean}: {current_stock} → {new_stock}")
                        modified += 1
        
        if modified:
            logger.info(f"✅ Synchronisation terminée: {modified} produit(s) mis à jour")
        else:
            logger.info("✅ Synchronisation terminée: Aucune modification nécessaire")
            
    except Exception as e:
        logger.exception(f"❌ Erreur lors de la synchronisation: {e}")

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="sync_job")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))

# ====================== ROUTES ======================
@app.route("/")
def home():
    """Page d'accueil"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NovaEngel → Shopify Sync</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .card { 
                background: #f5f5f5; 
                padding: 20px; 
                margin: 15px 0; 
                border-radius: 8px;
                border-left: 4px solid #4CAF50;
            }
            a { color: #2196F3; text-decoration: none; }
            a:hover { text-decoration: underline; }
            code { background: #eee; padding: 2px 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>🔄 NovaEngel → Shopify Synchronisation</h1>
        
        <div class="card">
            <h3>📊 Statut</h3>
            <p>Synchronisation automatique toutes les heures</p>
            <p>Dernière sync: <span id="lastSync">En cours...</span></p>
        </div>
        
        <div class="card">
            <h3>🔧 Routes disponibles</h3>
            <ul>
                <li><a href="/health">/health</a> - Vérification santé</li>
                <li><a href="/sync?key=VOTRE_CLE">/sync?key=XXX</a> - Synchronisation manuelle</li>
                <li><a href="/test-novaengel">/test-novaengel</a> - Test envoi commande</li>
                <li><a href="/find-product-ids?sku=8436097094189">/find-product-ids</a> - Trouver IDs produit</li>
                <li><a href="/debug-products">/debug-products</a> - Voir produits NovaEngel</li>
            </ul>
        </div>
        
        <div class="card">
            <h3>📦 Webhook Shopify</h3>
            <p>URL: <code>https://votre-app.onrender.com/shopify/order-created</code></p>
            <p>Événement: <code>orders/create</code></p>
        </div>
        
        <script>
            fetch('/health')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('lastSync').textContent = 
                        new Date(data.timestamp * 1000).toLocaleString();
                });
        </script>
    </body>
    </html>
    """

@app.route("/health")
def health():
    """Route de santé"""
    return jsonify({
        "status": "healthy",
        "service": "NovaEngel-Shopify Sync",
        "version": "1.0",
        "timestamp": time.time(),
        "endpoints": {
            "webhook": "/shopify/order-created",
            "sync": "/sync?key=SECRET_KEY",
            "test": "/test-novaengel",
            "health": "/health"
        }
    }), 200

@app.route("/sync")
def manual_sync():
    """Synchronisation manuelle"""
    key = request.args.get("key", "")
    if key != SECRET_KEY:
        return jsonify({"error": "Clé invalide"}), 403
    
    # Lancer la sync dans un thread
    threading.Thread(target=sync_all_products).start()
    
    return jsonify({
        "status": "sync lancée",
        "message": "La synchronisation a démarré en arrière-plan"
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("🎯 WEBHOOK SHOPIFY RECEIVED")
    
    try:
        # 1. Récupérer la commande
        order = request.get_json(force=True)
        
        # 2. Log les infos importantes
        logger.info(f"📦 Commande #{order.get('name', 'N/A')}")
        logger.info(f"📧 Client: {order.get('email', 'N/A')}")
        logger.info(f"💰 Total: {order.get('total_price', 'N/A')} {order.get('currency', 'N/A')}")
        logger.info(f"📝 Items: {len(order.get('line_items', []))}")
        
        # 3. Envoyer à NovaEngel dans un thread séparé
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        # 4. Réponse immédiate à Shopify
        return jsonify({
            "status": "processing",
            "message": "Commande envoyée à NovaEngel",
            "order_number": order.get('name')
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Erreur webhook: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route("/test-novaengel", methods=["GET"])
def test_novaengel():
    """Test d'envoi de commande à NovaEngel"""
    logger.info("🧪 TEST COMMANDE NOVAENGEL")
    
    # Commande de test
    test_order = {
        "name": f"TEST{int(time.time()) % 10000}",
        "email": "test@example.com",
        "total_price": "45.99",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "8436097094189",  # REMPLACEZ par vos vrais SKUs
                "quantity": 1,
                "price": "25.50"
            },
            {
                "sku": "8436097094190",  # REMPLACEZ par vos vrais SKUs
                "quantity": 2,
                "price": "10.25"
            }
        ],
        "shipping_address": {
            "first_name": "Jean",
            "last_name": "Dupont",
            "address1": "123 Avenue des Champs-Élysées",
            "city": "Paris",
            "zip": "75008",
            "country": "France",
            "country_code": "FR",
            "province": "Île-de-France",
            "phone": "0612345678"
        }
    }
    
    # Envoyer la commande (directement, pas dans un thread pour voir les logs)
    result = send_order_to_novaengel(test_order)
    
    return jsonify({
        "status": "test_completed",
        "order": test_order["name"],
        "success": result,
        "message": "Vérifiez les logs pour les détails"
    }), 200

@app.route("/find-product-ids", methods=["GET"])
def find_product_ids():
    """Trouve les IDs NovaEngel pour vos SKUs"""
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Impossible d'obtenir le token NovaEngel"}), 500
    
    # Récupérer les SKUs depuis les paramètres
    skus = request.args.getlist("sku")
    if not skus:
        return jsonify({
            "error": "Fournissez au moins un SKU",
            "example": "/find-product-ids?sku=8436097094189&sku=8436097094190"
        }), 400
    
    try:
        # Récupérer tous les produits (version paginée)
        all_products = []
        page = 0
        elements = 100
        
        logger.info(f"🔍 Recherche IDs pour {len(skus)} SKUs...")
        
        while True:
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/{elements}/en"
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            
            if r.status_code != 200:
                break
            
            products = r.json()
            if not products:
                break
            
            all_products.extend(products)
            
            if len(products) < elements:
                break
            page += 1
        
        # Rechercher chaque SKU
        results = {}
        for sku in skus:
            found = False
            for product in all_products:
                eans = product.get("EANS", [])
                if sku in eans:
                    results[sku] = {
                        "id": product.get("Id"),
                        "description": product.get("Description"),
                        "price": product.get("Price"),
                        "stock": product.get("Stock"),
                        "brand": product.get("BrandName")
                    }
                    found = True
                    break
            
            if not found:
                results[sku] = {"error": "SKU non trouvé dans NovaEngel"}
        
        # Créer un mapping pour copier-coller
        mapping = {}
        mapping_code = "# Copiez ceci dans orders.py:\nSKU_TO_ID = {"
        for sku, data in results.items():
            if "id" in data:
                mapping[sku] = data["id"]
                mapping_code += f'\n    "{sku}": {data["id"]},'
        mapping_code += "\n}"
        
        return jsonify({
            "count": len(skus),
            "found": len([r for r in results.values() if "id" in r]),
            "results": results,
            "mapping": mapping,
            "mapping_code": mapping_code
        }), 200
        
    except Exception as e:
        logger.exception(f"❌ Erreur recherche IDs: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/debug-products", methods=["GET"])
def debug_products():
    """Debug: voir les premiers produits NovaEngel"""
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Pas de token"}), 500
    
    try:
        # Récupérer 20 produits
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/20/en"
        r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
        
        if r.status_code != 200:
            return jsonify({"error": f"API: {r.status_code}", "text": r.text}), 500
        
        products = r.json()
        simplified = []
        
        for p in products:
            simplified.append({
                "Id": p.get("Id"),
                "EANs": p.get("EANS", []),
                "Description": p.get("Description", "")[:50] + "...",
                "Price": p.get("Price"),
                "Stock": p.get("Stock"),
                "Brand": p.get("BrandName")
            })
        
        return jsonify({
            "count": len(simplified),
            "products": simplified
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/check-token", methods=["GET"])
def check_token():
    """Vérifie si le token NovaEngel fonctionne"""
    token = get_novaengel_token()
    
    if token:
        # Tester avec une requête simple
        try:
            url = f"https://drop.novaengel.com/api/stock/update/{token}"
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
            
            return jsonify({
                "status": "token_valid",
                "token_preview": token[:8] + "...",
                "stock_api": r.status_code == 200,
                "message": "Token fonctionnel" if r.status_code == 200 else "Token invalide"
            }), 200
        except:
            return jsonify({
                "status": "token_error",
                "token_preview": token[:8] + "...",
                "message": "Erreur de connexion"
            }), 500
    else:
        return jsonify({
            "status": "no_token",
            "message": "Impossible d'obtenir un token. Vérifiez NOVA_USER et NOVA_PASS."
        }), 500

# ====================== START ======================
if __name__ == "__main__":
    logger.info("🚀 Démarrage de l'application...")
    logger.info(f"🏪 Store: {SHOPIFY_STORE}")
    logger.info("⏰ Sync automatique toutes les heures")
    
    # Démarrer une sync initiale après 3 secondes
    time.sleep(3)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    # Démarrer le serveur
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Serveur démarré sur le port {port}")
    
    # NOTE: En production sur Render, utilisez gunicorn
    # Pour le développement, Flask est OK
    app.run(host="0.0.0.0", port=port, threaded=True)