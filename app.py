from flask import Flask, request, jsonify
import threading
import logging
import os

from orders import send_order_to_novaengel

PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

app = Flask(_name_)

@app.route("/")
def home():
    return "Nova Engel Order Sync – RUNNING"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logger.info(f"🛒 Order received: {order.get('name')}")

        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()

        return jsonify({"status": "queued"}), 200

    except Exception as e:
        logger.exception("Webhook error")
        return jsonify({"error": str(e)}), 500

if _name_ == "_main_":
    app.run(host="0.0.0.0", port=PORT)