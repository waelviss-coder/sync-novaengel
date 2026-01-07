from flask import Flask, request, jsonify
import threading
import os
import hmac
import hashlib
import base64
import logging
from orders import send_order_to_novaengel

# ================= CONFIG =================
SHOPIFY_WEBHOOK_SECRET = os.environ.get("SHOPIFY_WEBHOOK_SECRET")  # facultatif pour tests

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================= APP =================
app = Flask(__name__)

# ================= SHOPIFY WEBHOOK VERIFY =================
def verify_shopify_webhook(data, hmac_header):
    # Pour Postman / tests manuels
    if not SHOPIFY_WEBHOOK_SECRET:
        return True

    digest = hmac.new(
        SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
        data,
        hashlib.sha256
    ).digest()

    calculated_hmac = base64.b64encode(digest).decode()
    return hmac.compare_digest(calculated_hmac, hmac_header or "")

# ================= ROUTES =================
@app.route("/")
def home():
    return "✅ Plureals → Nova Engel Connector ACTIVE"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        raw_data = request.data
        hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")

        if not verify_shopify_webhook(raw_data, hmac_header):
            logger.warning("❌ Webhook Shopify invalide")
            return jsonify({"error": "invalid webhook"}), 401

        order = request.get_json(force=True)
        threading.Thread(
            target=send_order_to_novaengel,
            args=(order,)
        ).start()

        return jsonify({"status": "order sent to Nova Engel"}), 200

    except Exception as e:
        logger.exception("❌ Erreur webhook Shopify")
        return jsonify({"error": str(e)}), 500

# ================= START =================
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
