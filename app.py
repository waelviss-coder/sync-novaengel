from flask import Flask, jsonify, request
import threading
import os
import time
import logging
from orders import send_order_to_novaengel, get_novaengel_token
import requests

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
    <head>
        <title>✅ Shopify → NovaEngel</title>
        <style>
            body { font-family: Arial; margin: 40px; }
            h1 { color: green; }
            .btn { display: inline-block; padding: 10px 20px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; margin: 5px; }
        </style>
    </head>
    <body>
        <h1>✅ Service Actif</h1>
        <p><strong>Mode:</strong> Recherche EAN réelle dans NovaEngel</p>
        <p><a class="btn" href="/test">Test Commande</a></p>
        <p><a class="btn" href="/debug-ean/8436097094189">Debug EAN</a></p>
        <p><a class="btn" href="/health">Santé</a></p>
    </body>
    </html>
    '''

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "NovaEngel EAN Finder",
        "timestamp": time.time()
    }), 200

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
        
        return jsonify({
            "status": "processing",
            "order_number": order_number
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Erreur webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/test")
def test():
    """Test commande"""
    test_order = {
        "name": f"TEST{int(time.time()) % 1000}",
        "email": "test@example.com",
        "line_items": [
            {
                "sku": "'8436097094189",
                "quantity": 2,
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
    
    success = send_order_to_novaengel(test_order)
    
    return jsonify({
        "test": "real_scan",
        "success": success,
        "message": "Vérifiez les logs pour l'ID réel trouvé"
    }), 200

@app.route("/debug-ean/<ean>")
def debug_ean(ean):
    """Debug complet pour un EAN"""
    token = get_novaengel_token()
    
    if not token:
        return "❌ Pas de token", 500
    
    try:
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
        response = requests.get(url, timeout=20)
        
        if response.status_code != 200:
            return f"❌ API error: {response.status_code}", 500
        
        products = response.json()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Debug EAN: {ean}</title>
            <style>
                body {{ font-family: Arial; margin: 20px; }}
                .product {{ border: 1px solid #ddd; padding: 15px; margin: 10px; }}
                .found {{ background: #d4edda; border-color: #c3e6cb; }}
                .byphasse {{ background: #fff3cd; border-color: #ffeaa7; }}
                h3 {{ color: #333; }}
                .ean {{ font-family: monospace; background: #f8f9fa; padding: 2px 5px; }}
                .match {{ color: green; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h1>🔍 Debug EAN: {ean}</h1>
            <p>Produits analysés: {len(products)}</p>
        """
        
        found = False
        for product in products:
            product_id = product.get("Id")
            description = product.get("Description", "")
            eans = product.get("EANS", [])
            sku = product.get("SKU", "")
            full_code = product.get("FullCode", "")
            barcode = product.get("Barcode", "")
            
            # Vérifier correspondance
            matches = []
            if ean in str(eans):
                matches.append("EANS")
            if ean == str(sku):
                matches.append("SKU")
            if ean == str(full_code):
                matches.append("FullCode")
            if ean == str(barcode):
                matches.append("Barcode")
            
            product_class = "product"
            if matches:
                product_class += " found"
                found = True
            
            if "BYPHASSE" in description.upper():
                product_class += " byphasse"
            
            html += f"""
            <div class="{product_class}">
                <h3>ID: {product_id} - {description[:80]}</h3>
                <p><strong>SKU:</strong> {sku}</p>
                <p><strong>FullCode:</strong> {full_code}</p>
                <p><strong>Barcode:</strong> {barcode}</p>
                <p><strong>EANS:</strong>"""
            
            for e in eans:
                e_str = str(e)
                if ean in e_str:
                    html += f'<span class="ean match">{e}</span> '
                else:
                    html += f'<span class="ean">{e}</span> '
            
            html += "</p>"
            
            if matches:
                html += f"<p class='match'>✅ CORRESPONDANCE: {', '.join(matches)}</p>"
            
            html += "</div>"
        
        if not found:
            html += f"<h2 style='color:red;'>❌ EAN {ean} NON TROUVÉ DANS LES 50 PREMIERS PRODUITS</h2>"
        
        html += "</body></html>"
        
        return html
        
    except Exception as e:
        return f"❌ Erreur: {e}", 500

if __name__ == "__main__":
    logger.info("🚀 Service démarré - Recherche EAN réelle")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)