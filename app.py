from flask import Flask, jsonify, request
import threading
import os
import logging

from orders import send_order_to_novaengel

# ================= CONFIG =================
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

# ================= APP =================
app = Flask(_name_)

# ================= ROUTES =================

@app.route("/")
def home():
    return "Nova Engel Sync – OK"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)

        logger.info(f"🛒 Commande Shopify reçue : {order.get('name')}")

        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,),
            daemon=True
        ).start()

        return jsonify({"status": "order sent to Nova Engel"}), 200

    except Exception as e:
        logger.exception("❌ Erreur webhook Shopify")
        return jsonify({"error": str(e)}), 500

# ================= START =================
if _name_ == "_main_":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        threaded=True
    )