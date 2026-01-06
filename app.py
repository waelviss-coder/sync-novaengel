from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock, load_products_cache, find_product_id, EAN_TO_ID_MAPPING

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

# ====================== SHOPIFY FUNCTIONS ======================
import requests

def shopify_request(method, endpoint, **kwargs):
    """Fonction helper pour requêtes Shopify"""
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10{endpoint}"
    headers = kwargs.get('headers', {})
    headers['X-Shopify-Access-Token'] = SHOPIFY_ACCESS_TOKEN
    kwargs['headers'] = headers
    
    try:
        response = requests.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur Shopify: {e}")
        raise

def get_all_shopify_products():
    """Récupère tous les produits Shopify"""
    try:
        products = []
        endpoint = "/products.json?limit=250"
        
        while endpoint:
            response = shopify_request("GET", endpoint)
            data = response.json()
            products.extend(data["products"])
            
            # Pagination
            link = response.headers.get("Link", "")
            endpoint = None
            if 'rel="next"' in link:
                for part in link.split(","):
                    if 'rel="next"' in part:
                        endpoint = part.split(";")[0].strip("<> ").replace(
                            f"https://{SHOPIFY_STORE}/admin/api/2024-10", ""
                        )
                        break
        
        logger.info(f"🛍️ {len(products)} produits Shopify récupérés")
        return products
    except Exception as e:
        logger.error(f"❌ Erreur produits Shopify: {e}")
        return []

def get_shopify_location_id():
    """Récupère l'ID de la location Shopify"""
    try:
        response = shopify_request("GET", "/locations.json")
        locations = response.json()["locations"]
        if locations:
            location_id = locations[0]["id"]
            logger.info(f"📍 Location ID: {location_id}")
            return location_id
        return None
    except:
        return None

def update_shopify_stock(inventory_item_id, location_id, stock):
    """Met à jour le stock Shopify"""
    try:
        payload = {
            "location_id": location_id,
            "inventory_item_id": inventory_item_id,
            "available": stock
        }
        shopify_request("POST", "/inventory_levels/set.json", json=payload)
        logger.info(f"📈 Stock mis à jour: {inventory_item_id} → {stock}")
        return True
    except:
        return False

# ====================== STOCK SYNC ======================
def sync_all_products():
    """Synchronise le stock NovaEngel → Shopify"""
    logger.info("🔄 Début synchronisation stock")
    
    try:
        # 1. Stock NovaEngel
        nova_stock = get_novaengel_stock()
        if not nova_stock:
            logger.error("❌ Impossible de récupérer le stock NovaEngel")
            return
        
        # 2. Produits Shopify
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()
        
        if not location_id:
            logger.error("❌ Impossible de récupérer la location Shopify")
            return
        
        # 3. Créer mapping SKU → Stock
        stock_map = {}
        for item in nova_stock:
            sku = str(item.get("Id", "")).strip()
            if sku:
                stock_map[sku] = item.get("Stock", 0)
        
        logger.info(f"📊 {len(stock_map)} produits dans le stock NovaEngel")
        
        # 4. Comparer et mettre à jour
        updated_count = 0
        for product in shopify_products:
            for variant in product["variants"]:
                sku = str(variant.get("sku", "")).strip()
                if sku in stock_map:
                    current_stock = variant.get("inventory_quantity", 0)
                    new_stock = stock_map[sku]
                    
                    if current_stock != new_stock:
                        if update_shopify_stock(
                            variant["inventory_item_id"],
                            location_id,
                            new_stock
                        ):
                            product_name = product['title'][:30] + ("..." if len(product['title']) > 30 else "")
                            logger.info(f"📦 {product_name} | {sku}: {current_stock}→{new_stock}")
                            updated_count += 1
        
        if updated_count > 0:
            logger.info(f"✅ Synchronisation terminée: {updated_count} produits mis à jour")
        else:
            logger.info("✅ Synchronisation: Aucune modification nécessaire")
            
    except Exception as e:
        logger.error(f"❌ Erreur synchronisation: {e}")

# ====================== SCHEDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", hours=1, id="stock_sync")
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ====================== ROUTES ======================
@app.route("/")
def home():
    """Page d'accueil"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NovaEngel ↔ Shopify Sync</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; max-width: 800px; }
            h1 { color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }
            .card { background: #f9f9f9; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #2196F3; }
            .success { border-left-color: #4CAF50; }
            .warning { border-left-color: #FF9800; }
            a { color: #2196F3; text-decoration: none; font-weight: bold; }
            a:hover { text-decoration: underline; }
            code { background: #eee; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
            .endpoint { margin: 10px 0; padding: 10px; background: #e8f4f8; border-radius: 4px; }
        </style>
    </head>
    <body>
        <h1>🔄 NovaEngel ↔ Shopify Synchronisation</h1>
        
        <div class="card success">
            <h3>✅ Service Actif</h3>
            <p>Synchronisation automatique toutes les heures</p>
            <p>Webhook Shopify configuré et fonctionnel</p>
        </div>
        
        <div class="card">
            <h3>🔧 Outils de Débug</h3>
            <div class="endpoint">
                <strong><a href="/test-order" target="_blank">/test-order</a></strong><br>
                <small>Teste l'envoi d'une commande à NovaEngel</small>
            </div>
            <div class="endpoint">
                <strong><a href="/find-ean/8436097094189" target="_blank">/find-ean/8436097094189</a></strong><br>
                <small>Trouve l'ID produit pour un EAN</small>
            </div>
            <div class="endpoint">
                <strong><a href="/view-mapping" target="_blank">/view-mapping</a></strong><br>
                <small>Affiche le mapping EAN → ID</small>
            </div>
            <div class="endpoint">
                <strong><a href="/sync-now?key=pl0reals" target="_blank">/sync-now?key=pl0reals</a></strong><br>
                <small>Synchronisation manuelle du stock</small>
            </div>
            <div class="endpoint">
                <strong><a href="/health" target="_blank">/health</a></strong><br>
                <small>Vérifie l'état du service</small>
            </div>
        </div>
        
        <div class="card warning">
            <h3>📦 Webhook Shopify</h3>
            <p>URL: <code>https://YOUR-APP.onrender.com/shopify/order-created</code></p>
            <p>Événement: <code>orders/create</code></p>
            <p>Format: JSON</p>
        </div>
        
        <script>
            // Mettre à jour l'heure actuelle
            document.getElementById('currentTime').textContent = new Date().toLocaleString();
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
        "timestamp": time.time(),
        "endpoints": {
            "webhook": "/shopify/order-created",
            "test": "/test-order",
            "sync": "/sync-now?key=SECRET_KEY",
            "mapping": "/view-mapping",
            "find_ean": "/find-ean/{ean}"
        }
    }), 200

@app.route("/sync-now")
def sync_now():
    """Synchronisation manuelle"""
    key = request.args.get("key", "")
    if key != SECRET_KEY:
        return jsonify({"error": "Clé invalide"}), 403
    
    # Lancer la sync dans un thread
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    return jsonify({
        "status": "sync_started",
        "message": "Synchronisation lancée en arrière-plan"
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("🎯 WEBHOOK SHOPIFY REÇU")
    
    try:
        # 1. Récupérer la commande
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        # 2. Log les informations
        logger.info(f"📦 Commande #{order_number}")
        logger.info(f"📧 Client: {order.get('email', 'N/A')}")
        logger.info(f"💰 Total: {order.get('total_price', 'N/A')}")
        logger.info(f"📝 Items: {len(order.get('line_items', []))}")
        
        # 3. Envoyer à NovaEngel dans un thread séparé
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        # 4. Répondre immédiatement à Shopify
        return jsonify({
            "status": "processing",
            "message": "Commande envoyée à NovaEngel",
            "order_number": order_number
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route("/test-order")
def test_order():
    """Test d'envoi de commande"""
    logger.info("🧪 TEST COMMANDE")
    
    # Commande de test
    test_order_data = {
        "name": f"TEST{int(time.time()) % 10000}",
        "email": "test@example.com",
        "total_price": "29.99",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "8436097094189",  # VOTRE EAN
                "quantity": 1,
                "price": "29.99"
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
    
    # Envoyer la commande (direct pour voir les logs)
    success = send_order_to_novaengel(test_order_data)
    
    return jsonify({
        "status": "test_completed",
        "success": success,
        "order_number": test_order_data["name"],
        "ean_tested": "8436097094189",
        "expected_id": 94189,
        "message": "Vérifiez les logs pour les détails"
    }), 200

@app.route("/find-ean/<ean>")
def find_ean(ean):
    """Trouve l'ID produit pour un EAN"""
    logger.info(f"🔍 Recherche EAN: {ean}")
    
    # Charger le cache
    load_products_cache()
    
    # Chercher l'ID
    product_id = find_product_id(ean)
    
    if product_id:
        return jsonify({
            "ean": ean,
            "product_id": product_id,
            "found": True,
            "message": f"ID trouvé: {product_id}"
        }), 200
    else:
        return jsonify({
            "ean": ean,
            "product_id": None,
            "found": False,
            "message": "EAN non trouvé",
            "mapping_actuel": EAN_TO_ID_MAPPING
        }), 404

@app.route("/view-mapping")
def view_mapping():
    """Affiche le mapping EAN → ID"""
    return jsonify({
        "mapping_count": len(EAN_TO_ID_MAPPING),
        "mapping": EAN_TO_ID_MAPPING,
        "instructions": "Copiez ce mapping dans EAN_TO_ID_MAPPING de orders.py"
    }), 200

@app.route("/reload-cache")
def reload_cache():
    """Recharge le cache des produits"""
    key = request.args.get("key", "")
    if key != SECRET_KEY:
        return jsonify({"error": "Clé invalide"}), 403
    
    # Recharger le cache
    cache = load_products_cache()
    
    return jsonify({
        "status": "cache_reloaded",
        "cache_size": len(cache),
        "sample": dict(list(cache.items())[:10])
    }), 200

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialise l'application"""
    logger.info("🚀 Initialisation de l'application...")
    logger.info(f"🏪 Store Shopify: {SHOPIFY_STORE}")
    
    # Charger le cache des produits au démarrage
    logger.info("📚 Préchargement du cache produits...")
    load_products_cache()
    
    # Synchronisation initiale
    time.sleep(5)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    logger.info("✅ Application initialisée")

# ====================== MAIN ======================
if __name__ == "__main__":
    # Initialisation
    initialize_app()
    
    # Démarrer le serveur
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Serveur démarré sur le port {port}")
    
    app.run(host="0.0.0.0", port=port, threaded=True)