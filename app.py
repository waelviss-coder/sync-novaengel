from flask import Flask, jsonify, request
import threading
import os
import time
import logging
from orders import send_order_to_novaengel

# ====================== LOGGER ======================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ====================== APP ======================
app = Flask(__name__)

@app.route("/")
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head><title>Shopify → NovaEngel</title></head>
    <body>
        <h1>✅ Service Actif</h1>
        <p>Mode: EAN direct → ID NovaEngel</p>
        <p><a href="/test">Test BYPHASSE</a></p>
        <p><a href="/test-ean/8436097094196">Test EAN 8436097094196</a></p>
    </body>
    </html>
    '''

@app.route("/shopify/order-created", methods=["POST"])
def shopify_webhook():
    """Webhook Shopify"""
    logger.info("🎯 WEBHOOK REÇU")
    
    try:
        order = request.get_json(force=True)
        order_number = order.get('name', 'N/A')
        
        logger.info(f"📦 Commande #{order_number}")
        
        # Envoyer
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()
        
        return jsonify({"status": "processing"}), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/test")
def test():
    """Test BYPHASSE"""
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "line_items": [
            {
                "sku": "'8436097094189",  # BYPHASSE avec apostrophe
                "quantity": 1,
                "price": "1.75"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "Client",
            "address1": "123 Rue",
            "city": "Paris",
            "zip": "75001",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "test": "byphasse",
        "success": success,
        "sku": "'8436097094189",
        "expected_id": 2731
    }), 200

@app.route("/test-ean/<ean>")
def test_ean(ean):
    """Test un EAN spécifique"""
    test_order = {
        "name": f"TEST-EAN-{int(time.time()) % 1000}",
        "email": "test@example.com",
        "line_items": [
            {
                "sku": f"'{ean}",  # Avec apostrophe comme Shopify
                "quantity": 1,
                "price": "10.00"
            }
        ],
        "shipping_address": {
            "first_name": "Test",
            "last_name": "EAN",
            "address1": "123 Test",
            "city": "Paris",
            "zip": "75001",
            "country_code": "FR",
            "phone": "0612345678"
        }
    }
    
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "test": "ean_specific",
        "ean": ean,
        "success": success,
        "message": f"Test EAN {ean} terminé"
    }), 200

if __name__ == "__main__":
    logger.info("🚀 Service démarré")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)