from flask import Flask, request, jsonify
import logging
from orders import send_order_to_novaengel

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "OK", 200


# --------------------------------------------------
# SHOPIFY WEBHOOK
# --------------------------------------------------
@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        logging.info("🎯 Webhook Shopify reçu")
        order = request.get_json()

        send_order_to_novaengel(order)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        logging.error(f"❌ Erreur traitement commande: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(port=5000)
