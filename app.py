from flask import Flask, request, jsonify
import logging
import os
from orders import send_order_to_novaengel

# ================= LOGGER =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ================= APP =================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Shopify → NovaEngel (EAN ONLY) actif"

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_webhook():
    logger.info("🎯 WEBHOOK SHOPIFY REÇU")

    try:
        order = request.get_json(force=True)
        success = send_order_to_novaengel(order)

        return jsonify({
            "status": "success" if success else "failed",
            "order": order.get("name")
        }), 200

    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
