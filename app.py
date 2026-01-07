from flask import Flask, request, jsonify
import logging
import os

from orders import send_order_to_novaengel

# --------------------------------------------------
# APP
# --------------------------------------------------
app = Flask(_name_)

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
        logging.info("🛒 Webhook Shopify reçu")

        order = request.get_json(force=True)
        send_order_to_novaengel(order)

        return jsonify({"status": "order sent to Nova Engel"}), 200

    except Exception as e:
        logging.exception("❌ Erreur traitement commande")
        return jsonify({"error": str(e)}), 500


# --------------------------------------------------
# START
# --------------------------------------------------
if _name_ == "_main_":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )