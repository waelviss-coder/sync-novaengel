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
        logger.debug(f"📈 Stock mis à jour: {inventory_item_id} → {stock}")
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
                            product_name = product['title'][:30] + ("..." if len(product['title']) > 30 else "")
                            logger.info(f"📦 {product_name} | SKU {sku}: {current_stock}→{new_stock}")
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
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>✅ NovaEngel ↔ Shopify Sync</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }
            h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
            .container { max-width: 800px; }
            .card { 
                background: #f8f9fa; 
                padding: 20px; 
                margin: 20px 0; 
                border-radius: 8px;
                border-left: 4px solid #3498db;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .success { border-left-color: #2ecc71; }
            .warning { border-left-color: #f39c12; }
            .info { border-left-color: #3498db; }
            a { 
                color: #2980b9; 
                text-decoration: none;
                font-weight: bold;
            }
            a:hover { text-decoration: underline; }
            code { 
                background: #e8f4f8; 
                padding: 3px 6px; 
                border-radius: 4px; 
                font-family: 'Courier New', monospace;
                font-size: 0.9em;
            }
            .endpoint { 
                margin: 10px 0; 
                padding: 12px; 
                background: #e8f4f8; 
                border-radius: 6px;
                border: 1px solid #b3e0f2;
            }
            .status { 
                display: inline-block; 
                padding: 4px 8px; 
                border-radius: 4px; 
                font-size: 0.8em; 
                font-weight: bold;
                margin-left: 10px;
            }
            .active { background: #d4edda; color: #155724; }
            .inactive { background: #f8d7da; color: #721c24; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✅ NovaEngel ↔ Shopify Synchronisation</h1>
            
            <div class="card success">
                <h3>🎉 Service Actif et Fonctionnel</h3>
                <p>• Synchronisation automatique toutes les heures</p>
                <p>• Webhook Shopify configuré et actif</p>
                <p>• Commandes envoyées à NovaEngel</p>
                <p>• Recherche automatique EAN → ID</p>
                <span class="status active">EN LIGNE</span>
            </div>
            
            <div class="card info">
                <h3>🔧 Outils de Test et Debug</h3>
                <div class="endpoint">
                    <strong><a href="/test" target="_blank">/test</a></strong><br>
                    <small>Teste une commande avec BYPHASSE (EAN: 8436097094189)</small>
                </div>
                <div class="endpoint">
                    <strong><a href="/health" target="_blank">/health</a></strong><br>
                    <small>Vérifie l\'état du service</small>
                </div>
                <div class="endpoint">
                    <strong><a href="/sync-now?key=pl0reals" target="_blank">/sync-now?key=pl0reals</a></strong><br>
                    <small>Synchronisation manuelle du stock</small>
                </div>
                <div class="endpoint">
                    <strong><a href="/check-ean/8436097094189" target="_blank">/check-ean/8436097094189</a></strong><br>
                    <small>Vérifie un EAN spécifique</small>
                </div>
            </div>
            
            <div class="card warning">
                <h3>📦 Webhook Shopify</h3>
                <p><strong>URL:</strong> <code>POST /shopify/order-created</code></p>
                <p><strong>Événement:</strong> <code>orders/create</code></p>
                <p><strong>Format:</strong> JSON</p>
                <p><strong>Fonctionnalité:</strong> Recherche automatique EAN → ID NovaEngel</p>
            </div>
            
            <div class="card">
                <h3>⚙️ Configuration</h3>
                <p><strong>Mode:</strong> Utilisation des EANs comme SKUs</p>
                <p><strong>Avantage:</strong> Pas de mapping manuel, recherche automatique</p>
                <p><strong>Shopify Store:</strong> plureals.myshopify.com</p>
                <p><strong>Dernière mise à jour:</strong> <span id="currentTime">Chargement...</span></p>
            </div>
        </div>
        
        <script>
            // Mettre à jour l'heure
            document.getElementById('currentTime').textContent = new Date().toLocaleString();
            
            // Vérifier la santé
            fetch('/health')
                .then(response => response.json())
                .then(data => {
                    console.log('Statut service:', data.status);
                })
                .catch(err => {
                    console.error('Erreur santé:', err);
                });
        </script>
    </body>
    </html>
    '''

@app.route("/health")
def health():
    """Route de santé"""
    return jsonify({
        "status": "healthy",
        "service": "NovaEngel-Shopify Sync",
        "version": "2.0",
        "timestamp": time.time(),
        "mode": "EAN-only automatic lookup",
        "features": [
            "shopify_webhook",
            "novaengel_order_sending",
            "automatic_ean_to_id_lookup",
            "stock_sync",
            "product_cache"
        ]
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
        "message": "Synchronisation lancée en arrière-plan",
        "timestamp": time.time()
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("🎯 WEBHOOK SHOPIFY REÇU")
    
    try:
        # 1. Récupérer la commande
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        # 2. Log les informations importantes
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
            "order_number": order_number,
            "mode": "automatic_ean_to_id_lookup",
            "timestamp": time.time()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({
            "error": str(e),
            "status": "error",
            "timestamp": time.time()
        }), 500

@app.route("/test")
def test():
    """Test d'envoi de commande avec BYPHASSE"""
    logger.info("🧪 TEST COMMANDE BYPHASSE")
    
    # Commande de test avec BYPHASSE
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "total_price": "1.99",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "8436097094189",  # BYPHASSE EAN
                "quantity": 2,
                "price": "1.99"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "BYPHASSE",
            "address1": "123 Rue de Test",
            "city": "Paris",
            "zip": "75001",
            "country": "France",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    # Envoyer la commande (direct pour voir les logs)
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "status": "test_completed",
        "success": success,
        "order_number": test_order["name"],
        "ean_tested": "8436097094189",
        "expected_id": 94189,
        "message": "Vérifiez les logs pour les détails",
        "timestamp": time.time()
    }), 200

@app.route("/check-ean/<ean>")
def check_ean(ean):
    """Vérifie un EAN spécifique"""
    logger.info(f"🔍 Vérification EAN: {ean}")
    
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Impossible d'obtenir le token"}), 500
    
    try:
        # Charger quelques produits pour vérifier
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        
        if response.status_code != 200:
            return jsonify({"error": f"API error: {response.status_code}"}), 500
        
        products = response.json()
        
        # Chercher l'EAN
        found_products = []
        for product in products:
            eans = product.get("EANS", [])
            if ean in eans:
                found_products.append({
                    "id": product.get("Id"),
                    "description": product.get("Description"),
                    "price": product.get("Price"),
                    "stock": product.get("Stock"),
                    "brand": product.get("BrandName")
                })
        
        return jsonify({
            "ean": ean,
            "found": len(found_products) > 0,
            "count": len(found_products),
            "products": found_products,
            "total_checked": len(products),
            "message": "EAN trouvé" if found_products else "EAN non trouvé dans les 50 premiers produits"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialise l'application"""
    logger.info("🚀 Initialisation de l'application...")
    logger.info(f"🏪 Shopify Store: {SHOPIFY_STORE}")
    logger.info("📦 Mode: EAN-only avec recherche automatique")
    logger.info("⏰ Synchronisation automatique: Toutes les heures")
    
    # Synchronisation initiale
    time.sleep(5)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    logger.info("✅ Application initialisée et prête")

# ====================== MAIN ======================
if __name__ == "__main__":
    # Initialisation
    initialize_app()
    
    # Démarrer le serveur
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Serveur démarré sur le port {port}")
    
    app.run(host="0.0.0.0", port=port, threaded=True)