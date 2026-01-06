from flask import Flask, jsonify, request, render_template_string
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock, get_novaengel_token
from orders import search_product_by_ean, get_cache_stats, load_product_cache

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
                sku = str(variant.get("sku", "")).strip().replace("'", "")
                if sku in stock_map:
                    current_stock = variant.get("inventory_quantity", 0)
                    new_stock = stock_map[sku]
                    
                    if current_stock != new_stock:
                        if update_shopify_stock(
                            variant["inventory_item_id"],
                            location_id,
                            new_stock
                        ):
                            product_name = product['title'][:30]
                            logger.info(f"📦 {product_name} | SKU {sku}: {current_stock}→{new_stock}")
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
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; background: #f5f5f5; }
            h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 15px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { 
                background: white; 
                padding: 25px; 
                margin: 20px 0; 
                border-radius: 10px;
                border-left: 5px solid #3498db;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .card:hover { transform: translateY(-2px); }
            .success { border-left-color: #27ae60; }
            .warning { border-left-color: #f39c12; }
            .danger { border-left-color: #e74c3c; }
            .info { border-left-color: #3498db; }
            .endpoint { 
                margin: 12px 0; 
                padding: 15px; 
                background: #e8f4f8; 
                border-radius: 8px;
                border: 1px solid #b3e0f2;
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #3498db;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 5px;
                font-weight: bold;
            }
            .btn:hover { background: #2980b9; }
            .btn-success { background: #27ae60; }
            .btn-warning { background: #f39c12; }
            .btn-danger { background: #e74c3c; }
            .status-badge {
                display: inline-block;
                padding: 5px 10px;
                border-radius: 20px;
                font-size: 0.8em;
                font-weight: bold;
                margin-left: 10px;
            }
            .online { background: #d4edda; color: #155724; }
            .offline { background: #f8d7da; color: #721c24; }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔄 NovaEngel ↔ Shopify Synchronisation</h1>
            
            <div class="card success">
                <h2>🎉 Service Actif et Opérationnel</h2>
                <p><strong>Mode:</strong> Synchronisation automatique EAN → ID</p>
                <p><strong>Statut:</strong> <span class="status-badge online">EN LIGNE</span></p>
                <p><strong>Dernière mise à jour:</strong> <span id="currentTime">...</span></p>
            </div>
            
            <div class="grid">
                <div class="card info">
                    <h3>🔧 Outils de Test</h3>
                    <div class="endpoint">
                        <a class="btn btn-success" href="/test" target="_blank">Test Commande BYPHASSE</a>
                        <p>Teste avec EAN: 8436097094189</p>
                    </div>
                    <div class="endpoint">
                        <a class="btn" href="/search-ean/8436097094189" target="_blank">Rechercher EAN</a>
                        <p>Recherche avancée d'un EAN</p>
                    </div>
                    <div class="endpoint">
                        <a class="btn" href="/cache-stats" target="_blank">Statistiques Cache</a>
                        <p>Voir le cache produits</p>
                    </div>
                </div>
                
                <div class="card warning">
                    <h3>⚡ Actions Rapides</h3>
                    <div class="endpoint">
                        <a class="btn btn-warning" href="/sync-now?key=pl0reals" target="_blank">Sync Manuelle</a>
                        <p>Synchronisation immédiate du stock</p>
                    </div>
                    <div class="endpoint">
                        <a class="btn" href="/health" target="_blank">Vérifier Santé</a>
                        <p>État du service</p>
                    </div>
                    <div class="endpoint">
                        <a class="btn" href="/debug-novaengel" target="_blank">Debug NovaEngel</a>
                        <p>Voir produits NovaEngel</p>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>📦 Webhook Shopify</h3>
                <p><strong>URL:</strong> <code>POST /shopify/order-created</code></p>
                <p><strong>Événement:</strong> <code>orders/create</code></p>
                <p><strong>Fonctionnalité:</strong> Recherche automatique EAN → ID</p>
                <p><strong>Statut:</strong> ✅ Actif</p>
            </div>
            
            <div class="card success">
                <h3>✅ Fonctionnalités Actives</h3>
                <ul>
                    <li>✅ Synchronisation automatique stock (toutes les heures)</li>
                    <li>✅ Webhook commandes Shopify</li>
                    <li>✅ Recherche EAN automatique</li>
                    <li>✅ Cache produits optimisé</li>
                    <li>✅ Gestion des erreurs complète</li>
                    <li>✅ Support multi-formats EAN</li>
                </ul>
            </div>
        </div>
        
        <script>
            document.getElementById('currentTime').textContent = new Date().toLocaleString();
            
            fetch('/health')
                .then(r => r.json())
                .then(data => console.log('Service:', data.status))
                .catch(err => console.error('Erreur:', err));
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
        "version": "3.0",
        "timestamp": time.time(),
        "features": [
            "automatic_stock_sync",
            "shopify_webhook",
            "ean_to_id_mapping",
            "product_cache",
            "error_handling"
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
    logger.info("🎯 WEBHOOK SHOPIFY RECEIVED")
    
    try:
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        logger.info(f"📦 Commande #{order_number}")
        logger.info(f"📧 Client: {order.get('email', 'N/A')}")
        logger.info(f"📝 Items: {len(order.get('line_items', []))}")
        
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

@app.route("/test")
def test():
    """Test d'envoi de commande avec BYPHASSE"""
    logger.info("🧪 TEST COMMANDE BYPHASSE")
    
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "total_price": "1.99",
        "currency": "EUR",
        "line_items": [
            {
                "sku": "8436097094189",
                "quantity": 1,
                "price": "1.99",
                "title": "BYPHASSE Lip Balm"
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
    
    # Envoyer la commande
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "status": "test_completed",
        "success": success,
        "order_number": test_order["name"],
        "ean_tested": "8436097094189",
        "timestamp": time.time()
    }), 200

@app.route("/search-ean/<ean>")
def search_ean(ean):
    """Recherche avancée d'un EAN"""
    logger.info(f"🔍 Recherche EAN: {ean}")
    
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Pas de token"}), 500
    
    product_id = search_product_by_ean(ean, token)
    
    if product_id:
        return jsonify({
            "ean": ean,
            "found": True,
            "product_id": product_id,
            "message": f"Produit trouvé: ID {product_id}"
        }), 200
    else:
        return jsonify({
            "ean": ean,
            "found": False,
            "message": "EAN non trouvé"
        }), 404

@app.route("/cache-stats")
def cache_stats():
    """Affiche les statistiques du cache"""
    stats = get_cache_stats()
    
    return jsonify({
        "cache_stats": stats,
        "timestamp": time.time()
    }), 200

@app.route("/debug-novaengel")
def debug_novaengel():
    """Debug direct des produits NovaEngel"""
    token = get_novaengel_token()
    if not token:
        return "❌ Pas de token NovaEngel", 500
    
    try:
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        
        if response.status_code != 200:
            return f"❌ HTTP {response.status_code}", 500
        
        products = response.json()
        
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug NovaEngel</title>
            <style>
                body { font-family: Arial; margin: 20px; }
                .product { border: 1px solid #ddd; padding: 15px; margin: 10px; border-radius: 5px; }
                .found { background: #d4edda; border-color: #c3e6cb; }
                .byphasse { background: #fff3cd; border-color: #ffeaa7; }
                h3 { color: #333; }
                .ean { font-family: monospace; background: #f8f9fa; padding: 2px 5px; }
            </style>
        </head>
        <body>
            <h1>🔍 Debug NovaEngel - 50 premiers produits</h1>
            <p>Total: %d produits</p>
        """ % len(products)
        
        byphasse_found = False
        for product in products:
            product_id = product.get("Id")
            description = product.get("Description", "")
            eans = product.get("EANS", [])
            sku = product.get("SKU", "")
            
            product_class = "product"
            if "8436097094189" in str(eans) or "BYPHASSE" in description.upper():
                product_class += " byphasse"
                byphasse_found = True
            
            html += f"""
            <div class="{product_class}">
                <h3>ID: {product_id} - {description[:80]}</h3>
                <p><strong>SKU:</strong> {sku}</p>
                <p><strong>EANS:</strong>"""
            
            for ean in eans:
                html += f'<span class="ean">{ean}</span> '
            
            html += "</p>"
            
            if "8436097094189" in str(eans):
                html += "<p style='color:green; font-weight:bold;'>✅ BYPHASSE TROUVÉ!</p>"
            
            html += "</div>"
        
        if not byphasse_found:
            html += "<h2 style='color:red;'>⚠️ BYPHASSE NON TROUVÉ DANS LES 50 PREMIERS PRODUITS</h2>"
        
        html += "</body></html>"
        
        return html
        
    except Exception as e:
        return f"❌ Erreur: {e}", 500

@app.route("/preload-cache")
def preload_cache():
    """Précharge le cache NovaEngel"""
    key = request.args.get("key", "")
    if key != SECRET_KEY:
        return jsonify({"error": "Clé invalide"}), 403
    
    token = get_novaengel_token()
    if not token:
        return jsonify({"error": "Pas de token"}), 500
    
    load_product_cache(token, force_reload=True)
    stats = get_cache_stats()
    
    return jsonify({
        "status": "cache_preloaded",
        "stats": stats,
        "timestamp": time.time()
    }), 200

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialise l'application"""
    logger.info("🚀 Initialisation...")
    logger.info(f"🏪 Store Shopify: {SHOPIFY_STORE}")
    logger.info("📊 Mode: EAN-only avec recherche automatique")
    
    # Synchronisation initiale
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