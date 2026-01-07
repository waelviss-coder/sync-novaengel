from flask import Flask, jsonify, request
import threading
import os
import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel, get_novaengel_stock

# ====================== CONFIG ======================
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# ====================== SYNC ======================
def sync_all_products():
    try:
        logging.info("🔄 Début synchronisation avec Nova Engel...")
        stocks = get_novaengel_stock()
        logging.info(f"📊 Stock Nova Engel récupéré: {len(stocks)} produits")
        # Ici tu peux ajouter la logique Shopify pour mettre à jour le stock
    except Exception as e:
        logging.error(f"❌ Erreur synchronisation: {e}")

# ====================== SCHEDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="sync_job")
scheduler.start()

# ====================== ROUTES ======================
@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify – AUTOMATIQUE TOUTES LES HEURES</h3>"

@app.route("/sync")
def manual_sync():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync lancée"}), 200

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        logging.info(f"📦 Commande Shopify reçue: {order.get('name')}")
        result = send_order_to_novaengel(order)
        logging.info(f"✅ Commande envoyée à Nova Engel: {result}")
        return jsonify({"status": "order sent to Nova Engel", "nova_result": result}), 200
    except Exception as e:
        logging.exception("❌ Erreur webhook Shopify")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logging.info("Démarrage du serveur Flask...")
    app.run(host="0.0.0.0", port=port)
