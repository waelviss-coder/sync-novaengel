from flask import Flask, request, jsonify
import threading
import logging
import os
from orders import send_order_to_novaengel

# ================= CONFIG =================
PORT = int(os.environ.get("PORT", 8080))

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================= APP =================
app = Flask(__name__)

# ================= ROUTES =================
@app.route("/")
def home():
    return "✅ Sync Plureals → Nova Engel ACTIVE"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)

        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,)
        ).start()

        return jsonify({"status": "order received"}), 200

    except Exception as e:
        logger.exception("❌ Erreur réception commande Shopify")
        return jsonify({"error": str(e)}), 500

# ================= START =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
