from flask import Flask, jsonify, request
import logging
import os

from orders import send_order_to_novaengel

app = Flask(_name_)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

@app.route("/")
def home():
    return "Nova Engel Sync OK", 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        result = send_order_to_novaengel(order)
        return jsonify({"status": "sent", "result": result}), 200
    except Exception as e:
        logging.exception("Erreur webhook commande")
        return jsonify({"error": str(e)}), 500


if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))