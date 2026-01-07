from flask import Flask, request, jsonify
import threading
import time
import logging
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import os
from orders import send_order_to_novaengel

# ====================== CONFIG ======================
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# ====================== SYNC ======================
def sync_all_products():
    print("\nDÉBUT SYNCHRONISATION AUTOMATIQUE")
    try:
        # Ici ton code Nova Engel → Shopify pour mettre à jour les stocks
        print("SYNC exécuté (mettre le code réel ici)")
    except Exception as e:
        print(f"ERREUR SYNC : {e}")

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="sync_job")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))

# ====================== ROUTES ======================
@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify – AUTOMATIQUE TOUTES LES HEURES</h3>"

@app.route("/sync")
def manual_sync():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync lancée"}), 200

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

# ====================== LOCAL DEV ======================
if __name__ == "__main__":
    print("Démarrage local – première sync dans 10 secondes…")
    time.sleep(10)
    threading.Thread(target=sync_all_products).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
