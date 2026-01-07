from flask import Flask, jsonify, request
import threading
import logging
import os

from orders import send_order_to_novaengel

# ================= APP =================
app = Flask(_name_)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

# ================= ROUTES =================

@app.route("/")
def home():
    return "Sync NovaEngel OK"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logger.info(f"🛒 Order received: {order.get('name')}")

        # Thread pour répondre vite à Shopify
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()

        return jsonify({"status": "order queued"}), 200

    except Exception as e:
        logger.exception("Erreur webhook commande")
        return jsonify({"error": str(e)}), 500

# ================= START =================
if _name_ == "_main_":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )