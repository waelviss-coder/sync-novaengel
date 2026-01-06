from flask import Flask, jsonify, request
import threading
import os
import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel  # uniquement commandes

# ====================== CONFIG ======================
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# ====================== ROUTES ======================
@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify – Webhook commandes uniquement</h3>"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logging.info(f"🔔 Nouvelle commande reçue : {order.get('name', 'TEST')}")
        send_order_to_novaengel(order)
        return jsonify({"status": "order sent to NovaEngel"}), 200
    except Exception as e:
        logging.exception("Erreur lors de l'envoi de la commande à NovaEngel")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    logging.info("Démarrage du serveur Flask – prêt à recevoir les commandes Shopify")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
