from flask import Flask, jsonify, request
import logging
import os
from orders import send_order_to_novaengel

SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "<h3>Nova Engel Connector – Orders OK ✅</h3>"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logging.info(f"📦 Commande reçue : {order.get('name')}")
        result = send_order_to_novaengel(order)
        return jsonify({
            "status": "order processed",
            "result": result
        }), 200
    except Exception as e:
        logging.exception("❌ Erreur Nova Engel")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
