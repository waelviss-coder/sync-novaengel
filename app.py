from flask import Flask, jsonify, request
import threading
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler

# ====================== LOGGER ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ====================== APP ======================
app = Flask(__name__)

# ====================== CONFIG ======================
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE", "plureals.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

# Import APRÈS la config
from orders import send_order_to_novaengel

# ====================== ROUTES ESSENTIELLES ======================
@app.route("/")
def home():
    """Page d'accueil simple et rapide"""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>✅ Shopify → NovaEngel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; text-align: center; }
            h1 { color: #2c3e50; }
            .status { 
                display: inline-block; 
                padding: 10px 20px; 
                background: #27ae60; 
                color: white; 
                border-radius: 5px; 
                margin: 20px 0; 
            }
            .btn {
                display: inline-block;
                padding: 10px 20px;
                background: #3498db;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                margin: 10px;
            }
        </style>
    </head>
    <body>
        <h1>✅ Shopify → NovaEngel</h1>
        <div class="status">SERVICE ACTIF</div>
        <p><strong>Mode:</strong> Envoi direct des commandes</p>
        <p><a class="btn" href="/health">Vérifier santé</a></p>
        <p><a class="btn" href="/test">Test rapide</a></p>
        <p><small>Render optimisé - Version 1.0</small></p>
    </body>
    </html>
    '''

@app.route("/health")
def health():
    """Health check pour Render"""
    return jsonify({
        "status": "healthy",
        "service": "shopify-novaengel",
        "timestamp": time.time(),
        "environment": "production"
    }), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify - OPTIMISÉ pour Render"""
    logger.info("🎯 Webhook reçu")
    
    try:
        # 1. Valider rapidement
        order = request.get_json(force=True)
        if not order:
            return jsonify({"error": "Données manquantes"}), 400
        
        order_number = order.get('name', 'N/A')
        logger.info(f"📦 Commande #{order_number}")
        
        # 2. Envoyer immédiatement dans un thread (non bloquant)
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        # 3. Répondre vite à Shopify (< 5s)
        return jsonify({
            "status": "processing",
            "order_number": order_number,
            "timestamp": time.time()
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({"error": "Erreur de traitement"}), 500

@app.route("/test")
def test():
    """Test rapide et simple"""
    logger.info("🧪 Test rapide")
    
    # Commande de test minimaliste
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "line_items": [
            {
                "sku": "'8436097094189",  # BYPHASSE
                "quantity": 1,
                "price": "1.75"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "Client",
            "address1": "123 Rue Test",
            "city": "Paris",
            "zip": "75001",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    # Envoyer directement (pas de thread pour le test)
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "test": "completed",
        "success": success,
        "product": "BYPHASSE Lip Balm",
        "sku": "'8436097094189",
        "timestamp": time.time()
    }), 200

# ====================== INITIALISATION ======================
def initialize_app():
    """Initialisation rapide"""
    logger.info("🚀 Initialisation Render...")
    logger.info(f"🏪 Store: {SHOPIFY_STORE}")
    logger.info("✅ Prêt à recevoir des commandes")

# ====================== MAIN ======================
if __name__ == "__main__":
    # Initialisation
    initialize_app()
    
    # Port Render
    port = int(os.environ.get("PORT", 10000))
    
    # Config pour production
    logger.info(f"🌐 Démarrage sur le port {port}")
    
    # Important: désactiver debug et reloader pour Render
    app.run(
        host="0.0.0.0", 
        port=port, 
        threaded=True,
        debug=False  # ← DÉSACTIVER DEBUG pour Render!
    )