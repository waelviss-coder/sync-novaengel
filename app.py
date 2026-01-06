from flask import Flask, jsonify, request
import threading
import os
import time
import logging
from orders import send_order_to_novaengel

# ====================== LOGGER ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# ====================== APP ======================
app = Flask(__name__)

@app.route("/")
def home():
    """Page d'accueil"""
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Shopify → NovaEngel</title></head>
    <body>
        <h1>✅ Shopify → NovaEngel</h1>
        <p>Service actif - Envoi direct des commandes</p>
        <p><a href="/test">Test BYPHASSE</a></p>
        <p><a href="/health">Vérifier</a></p>
    </body>
    </html>
    '''

@app.route("/health")
def health():
    """Santé"""
    return jsonify({"status": "ok", "time": time.time()}), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    """Webhook Shopify"""
    logger.info("📦 COMMANDE REÇUE")
    
    try:
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        logger.info(f"Commande #{order_number}")
        
        # Envoyer
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        return jsonify({"status": "processing"}), 200
        
    except Exception as e:
        logger.error(f"Erreur: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/test")
def test():
    """Test BYPHASSE"""
    logger.info("🧪 TEST")
    
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "line_items": [
            {
                "sku": "'8436097094189",
                "quantity": 1,
                "price": "1.75"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "Client",
            "address1": "123 Test",
            "city": "Paris",
            "zip": "75001",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "success": success,
        "test": "byphasse"
    }), 200

if __name__ == "__main__":
    logger.info("🚀 Service démarré")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)