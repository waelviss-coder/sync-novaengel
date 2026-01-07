from flask import Flask, request, jsonify
import logging
import os
from orders import send_order_to_novaengel

# --------------------------------------------------
# APP
# --------------------------------------------------
app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --------------------------------------------------
# HEALTH CHECK (OBLIGATOIRE POUR RENDER)
# --------------------------------------------------
@app.route("/", methods=["GET"])
def health():
    return "OK", 200


# --------------------------------------------------
# SHOPIFY ORDER WEBHOOK
# --------------------------------------------------
@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logging.info(f"📦 Commande Shopify reçue: {order.get('name')}")

        send_order_to_novaengel(order)

        return jsonify({"status": "order sent to Nova Engel"}), 200

    except Exception as e:
        logging.exception("❌ Erreur webhook Shopify")
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# START (DEV LOCAL UNIQUEMENT)
# --------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
