from flask import Flask, jsonify, request
import logging
import os
from orders import send_order_to_novaengel

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

@app.route("/")
def home():
    return "Nova Engel Connector READY"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():

    order = request.get_json(silent=True)

    if not order:
        logging.error("❌ Invalid Shopify payload")
        return jsonify({"error": "invalid payload"}), 400

    logging.info(f"📦 Order received: {order.get('name')}")

    try:
        result = send_order_to_novaengel(order)

        logging.info(f"📩 Nova result: {result}")

        return jsonify({
            "status": "ok",
            "result": result
        }), 200

    except Exception as e:
        logging.exception("❌ Nova processing error")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
