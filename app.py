from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock, EAN_TO_ID

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
        return True
    except:
        return False

# ====================== STOCK SYNC ======================
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
        
        # 3. Créer mapping ID → Stock
        stock_map = {}
        for item in nova_stock:
            item_id = str(item.get("Id", "")).strip()
            if item_id:
                stock_map[item_id] = item.get("Stock", 0)
        
        logger.info(f"📊 {len(stock_map)} produits dans le mapping")
        
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
                            updated_count += 1
        
        if updated_count > 0:
            logger.info(f"✅ {updated_count} produits mis à jour")
        else:
            logger.info("✅ Aucune modification nécessaire")
            
    except Exception as e:
        logger.error(f"❌ Erreur sync: {e}")

# ====================== SCHEDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", hours=1)
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
        <title>✅ NovaEngel ↔ Shopify - FONCTIONNEL</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #4CAF50; }
            .card { background: #f5f5f5; padding: 20px; margin: 15px 0; border-radius: 8px; }
            a { color: #2196F3; text-decoration: none; font-weight: bold; }
            a:hover { text-decoration: underline; }
            .success { background: #d4edda; border-left: 5px solid #28a745; }
            .warning { background: #fff3cd; border-left: 5px solid #ffc107; }
        </style>
    </head>
    <body>
        <h1>✅ Sync NovaEngel ↔ Shopify - FONCTIONNEL</h1>
        
        <div class="card success">
            <h3>🎉 Service Actif</h3>
            <p>• Synchronisation automatique toutes les heures</p>
            <p>• Webhook Shopify configuré</p>
            <p>• Commandes envoyées à NovaEngel</p>
        </div>
        
        <div class="card">
            <h3>🔧 Routes de test</h3>
            <p><a href="/test-command" target="_blank">/test-command</a> - Teste une commande</p>
            <p><a href="/view-mapping" target="_blank">/view-mapping</a> - Voir le mapping EAN→ID</p>
            <p><a href="/sync-now?key=pl0reals" target="_blank">/sync-now?key=pl0reals</a> - Sync manuelle</p>
            <p><a href="/health" target="_blank">/health</a> - Vérifier santé</p>
        </div>
        
        <div class="card warning">
            <h3>📦 Webhook Shopify</h3>
            <p><strong>URL:</strong> <code>/shopify/order-created</code></p>
            <p><strong>Événement:</strong> <code>orders/create</code></p>
            <p><strong>Méthode:</strong> <code>POST</code></p>
        </div>
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
        "mapping_count": len(EAN_TO_ID)
    }), 200

@app.route("/sync-now")
def sync_now():
    """Synchronisation manuelle"""
    key = request.args.get("key", "")
    if key != SECRET_KEY:
        return jsonify({"error": "Clé invalide"}), 403
    
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    return jsonify({
        "status": "sync_started",
        "message": "Synchronisation lancée"
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("🎯 WEBHOOK SHOPIFY RECEIVED")
    
    try:
        # 1. Récupérer la commande
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        # 2. Log les informations
        logger.info(f"📦 Commande #{order_number}")
        logger.info(f"📧 Client: {order.get('email', 'N/A')}")
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

@app.route("/test-command")
def test_command():
    """Test d'envoi de commande"""
    logger.info("🧪 TEST COMMANDE")
    
    # Commande de test avec ID CONNU
    test_order_data = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "total_price": "42.00",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "87061",  # ← ID DIRECT de SHISEIDO
                "quantity": 1,
                "price": "42.00"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "Client",
            "address1": "123 Rue Test",
            "city": "Paris",
            "zip": "75001",
            "country": "France",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    # Envoyer la commande
    success = send_order_to_novaengel(test_order_data)
    
    return jsonify({
        "status": "test_completed",
        "success": success,
        "order_number": test_order_data["name"],
        "product_tested": "ID 87061 (SHISEIDO)",
        "message": "Vérifiez les logs pour les détails"
    }), 200

@app.route("/view-mapping")
def view_mapping():
    """Affiche le mapping EAN → ID"""
    return jsonify({
        "mapping_count": len(EAN_TO_ID),
        "mapping": EAN_TO_ID,
        "instructions": "Ce mapping doit être rempli dans orders.py"
    }), 200

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialise l'application"""
    logger.info("🚀 Initialisation...")
    logger.info(f"🏪 Store Shopify: {SHOPIFY_STORE}")
    logger.info(f"📊 Mapping: {len(EAN_TO_ID)} EANs configurés")
    
    # Synchronisation initiale
    time.sleep(3)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    logger.info("✅ Application initialisée")

# ====================== MAIN ======================
if __name__ == "__main__":
    # Initialisation
    initialize_app()
    
    # Démarrer le serveur
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Serveur sur le port {port}")
    
    app.run(host="0.0.0.0", port=port, threaded=True)