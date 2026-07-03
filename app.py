from flask import Flask, jsonify, request
import logging
import os
from orders import send_order_to_novaengel

app = Flask(__name__)   # ✅ CORRECT
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "<h3>Nova Engel Connector – READY ✅</h3>"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    order = request.get_json(force=True)

    logging.info(f"📦 Commande Shopify reçue : {order.get('name')}")
    logging.info(f"FULL ORDER: {order}")   # 👈 AJOUT IMPORTANT

    try:
        result = send_order_to_novaengel(order)
        logging.info(f"RESULT NOVA: {result}")  # 👈 AJOUT IMPORTANT

    except Exception as e:
        logging.error(f"❌ ERREUR NOVA: {str(e)}")
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "status": "sent to Nova Engel",
        "result": result
    }), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
