from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock, get_novaengel_token
from orders import search_ean_advanced, get_cache_info, load_product_cache, get_product_info

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
        
        logger.info(f"🛍️ {len(products)} produits Shopify")
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
            return locations[0]["id"]
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
        # Stock NovaEngel
        nova_stock = get_novaengel_stock()
        if not nova_stock:
            logger.error("❌ Impossible de récupérer le stock NovaEngel")
            return
        
        # Produits Shopify
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()
        
        if not location_id:
            logger.error("❌ Impossible de récupérer la location Shopify")
            return
        
        # Mapping ID → Stock
        stock_map = {}
        for item in nova_stock:
            product_id = str(item.get("Id", "")).strip()
            if product_id:
                stock_map[product_id] = item.get("Stock", 0)
        
        logger.info(f"📊 {len(stock_map)} produits dans le mapping")
        
        # Comparer et mettre à jour
        updated_count = 0
        for product in shopify_products:
            for variant in product["variants"]:
                sku = str(variant.get("sku", "")).strip()
                
                # Chercher l'ID NovaEngel pour ce SKU
                token = get_novaengel_token()
                if token:
                    load_product_cache(token)
                    
                    # Utiliser la fonction de recherche
                    product_id = search_ean_advanced(sku, token)
                    
                    if product_id and str(product_id) in stock_map:
                        current_stock = variant.get("inventory_quantity", 0)
                        new_stock = stock_map[str(product_id)]
                        
                        if current_stock != new_stock:
                            if update_shopify_stock(
                                variant["inventory_item_id"],
                                location_id,
                                new_stock
                            ):
                                product_name = product['title'][:30]
                                logger.info(f"📦 {product_name} | ID {product_id}: {current_stock}→{new_stock}")
                                updated_count += 1
        
        if updated_count > 0:
            logger.info(f"✅ Synchronisation: {updated_count} produits mis à jour")
        else:
            logger.info("✅ Synchronisation: Aucune modification")
            
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
            body { font-family: Arial, sans-serif; margin: 40px; background: #f8f9fa; }
            h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; padding: 25px; margin: 20px 0; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
            .success { border-left: 5px solid #27ae60; }
            .warning { border-left: 5px solid #f39c12; }
            .info { border-left: 5px solid #3498db; }
            .btn { display: inline-block; padding: 10px 20px; background: #3498db; color: white; text-decoration: none; border-radius: 5px; margin: 5px; font-weight: bold; }
            .btn:hover { opacity: 0.9; }
            .btn-success { background: #27ae60; }
            .btn-warning { background: #f39c12; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
            .status { padding: 5px 10px; border-radius: 20px; font-size: 0.9em; font-weight: bold; }
            .online { background: #d4edda; color: #155724; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔄 NovaEngel ↔ Shopify Synchronisation</h1>
            
            <div class="card success">
                <h2>✅ Service Opérationnel</h2>
                <p><strong>Statut:</strong> <span class="status online">EN LIGNE</span></p>
                <p><strong>Mode:</strong> Synchronisation automatique EAN → ID</p>
                <p><strong>Dernière mise à jour:</strong> <span id="currentTime">...</span></p>
            </div>
            
            <div class="grid">
                <div class="card info">
                    <h3>🔧 Outils de Test</h3>
                    <p><a class="btn btn-success" href="/test-byphasse" target="_blank">Test BYPHASSE</a></p>
                    <p><a class="btn" href="/search/8436097094189" target="_blank">Rechercher EAN</a></p>
                    <p><a class="btn" href="/cache-info" target="_blank">Cache Info</a></p>
                </div>
                
                <div class="card warning">
                    <h3>⚡ Actions</h3>
                    <p><a class="btn btn-warning" href="/sync-now?key=pl0reals" target="_blank">Sync Manuelle</a></p>
                    <p><a class="btn" href="/health" target="_blank">Vérifier Santé</a></p>
                    <p><a class="btn" href="/debug-byphasse" target="_blank">Debug BYPHASSE</a></p>
                </div>
            </div>
            
            <div class="card info">
                <h3>📦 Produits Configurés</h3>
                <ul>
                    <li><strong>BYPHASSE Lip Balm:</strong> SKU <code>'8436097094189</code> → ID <strong>2731</strong></li>
                    <li><strong>Autre produit:</strong> SKU <code>'0729238187061</code> → ID <strong>87061</strong></li>
                </ul>
                <p>✅ Mapping forcé configuré pour ces produits</p>
            </div>
            
            <div class="card success">
                <h3>✅ Fonctionnalités</h3>
                <ul>
                    <li>✅ Sync automatique stock (toutes les heures)</li>
                    <li>✅ Webhook commandes Shopify</li>
                    <li>✅ Mapping EAN → ID NovaEngel</li>
                    <li>✅ Cache produits optimisé</li>
                    <li>✅ Gestion des erreurs</li>
                </ul>
            </div>
        </div>
        
        <script>
            document.getElementById('currentTime').textContent = new Date().toLocaleString();
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
        "version": "3.1",
        "timestamp": time.time(),
        "mappings_configured": [
            {"sku": "'8436097094189", "id": 2731, "product": "BYPHASSE Lip Balm"},
            {"sku": "'0729238187061", "id": 87061, "product": "Autre produit"}
        ]
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
        "message": "Synchronisation lancée",
        "timestamp": time.time()
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - Nouvelle commande"""
    logger.info("🎯 WEBHOOK SHOPIFY REÇU")
    
    try:
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        logger.info(f"📦 Commande #{order_number}")
        logger.info(f"📧 Client: {order.get('email', 'N/A')}")
        
        # Envoyer dans un thread séparé
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        return jsonify({
            "status": "processing",
            "message": "Commande envoyée à NovaEngel",
            "order_number": order_number,
            "timestamp": time.time()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/test-byphasse")
def test_byphasse():
    """Test spécifique BYPHASSE"""
    logger.info("🧪 TEST BYPHASSE")
    
    test_order = {
        "name": f"TESTBYPH{int(time.time()) % 1000}",
        "email": "test@byphasse.com",
        "line_items": [
            {
                "sku": "'8436097094189",  # SKU avec apostrophe comme dans Shopify
                "quantity": 1,
                "price": "1.75",
                "title": "MOISTURIZING LIP BALM 2 u - Woman"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "BYPHASSE",
            "address1": "123 Rue Test",
            "city": "Paris",
            "zip": "75001",
            "country": "FR",
            "phone": "0612345678"
        }
    }
    
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "status": "test_completed",
        "success": success,
        "order_number": test_order["name"],
        "sku_tested": "'8436097094189",
        "expected_id": 2731,
        "product": "BYPHASSE Lip Balm",
        "timestamp": time.time()
    }), 200

@app.route("/search/<ean>")
def search_ean(ean):
    """Recherche un EAN"""
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Pas de token"}), 500
    
    product_id = search_ean_advanced(ean, token)
    
    if product_id:
        product_info = get_product_info(product_id)
        return jsonify({
            "ean": ean,
            "found": True,
            "product_id": product_id,
            "product_info": product_info
        }), 200
    else:
        return jsonify({
            "ean": ean,
            "found": False,
            "message": "Non trouvé"
        }), 404

@app.route("/cache-info")
def cache_info():
    """Info cache"""
    info = get_cache_info()
    return jsonify(info), 200

@app.route("/debug-byphasse")
def debug_byphasse():
    """Debug BYPHASSE"""
    token = get_novaengel_token()
    if not token:
        return "❌ Pas de token", 500
    
    try:
        # Charger cache
        load_product_cache(token, force_reload=True)
        
        # Chercher BYPHASSE
        product_id = search_ean_advanced("8436097094189", token)
        
        if not product_id:
            return "<h1>❌ BYPHASSE non trouvé</h1>"
        
        product_info = get_product_info(product_id)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug BYPHASSE</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                .info {{ background: #e8f5e8; padding: 20px; border-radius: 10px; }}
                .key {{ font-weight: bold; color: #2c3e50; }}
                .value {{ color: #27ae60; }}
            </style>
        </head>
        <body>
            <h1>🔍 Debug BYPHASSE</h1>
            
            <div class="info">
                <h2>✅ PRODUIT TROUVÉ</h2>
                <p><span class="key">ID NovaEngel:</span> <span class="value">{product_id}</span></p>
        """
        
        if product_info:
            html += f"""
                <p><span class="key">Description:</span> {product_info.get('description', 'N/A')}</p>
                <p><span class="key">EANs:</span> {product_info.get('eans', [])}</p>
                <p><span class="key">SKU:</span> {product_info.get('sku', 'N/A')}</p>
                <p><span class="key">FullCode:</span> {product_info.get('full_code', 'N/A')}</p>
                <p><span class="key">Brand:</span> {product_info.get('brand', 'N/A')}</p>
                <p><span class="key">Price:</span> {product_info.get('price', 'N/A')} €</p>
            """
        
        html += f"""
                <h3>📌 Mapping Configuré</h3>
                <ul>
                    <li>SKU <code>'8436097094189</code> → ID <strong>2731</strong></li>
                    <li>SKU <code>8436097094189</code> → ID <strong>2731</strong></li>
                    <li>Code <code>094189</code> → ID <strong>2731</strong></li>
                    <li>Code <code>94189</code> → ID <strong>2731</strong></li>
                </ul>
                
                <p style="color:green; font-weight:bold;">
                    ✅ Prêt pour les commandes! Le produit sera envoyé avec l'ID {product_id}
                </p>
            </div>
            
            <p><a href="/test-byphasse" style="color:blue;">📦 Tester une commande BYPHASSE</a></p>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        return f"❌ Erreur: {e}", 500

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialise l'application"""
    logger.info("🚀 Initialisation...")
    logger.info(f"🏪 Store Shopify: {SHOPIFY_STORE}")
    logger.info("📊 Mapping BYPHASSE configuré: '8436097094189' → ID 2731")
    
    # Sync initiale
    time.sleep(3)
    threading.Thread(target=sync_all_products, daemon=True).start()
    
    logger.info("✅ Application initialisée")

# ====================== MAIN ======================
if __name__ == "__main__":
    # Initialisation
    initialize_app()
    
    # Démarrer le serveur
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Serveur sur le port {port}")
    
    app.run(host="0.0.0.0", port=port, threaded=True)