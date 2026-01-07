from flask import Flask, jsonify, request
import threading
import logging
import os
from orders import send_order_to_novaengel

# ====================== CONFIG ======================
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ====================== ROUTES ======================

@app.route("/")
def home():
    return "<h3>Nova Engel Connector – Webhook actif ✅</h3>"

@app.route("/sync")
def manual_sync():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    return jsonify({"status": "sync disabled (orders only)"}), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logging.info(f"📦 Commande Shopify reçue : {order.get('name')}")
        result = send_order_to_novaengel(order)
        return jsonify({
            "status": "sent to Nova Engel",
            "result": result
        }), 200
    except Exception as e:
        logging.exception("❌ Erreur envoi commande Nova Engel")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
