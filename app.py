from flask import Flask, jsonify, request
import threading
import requests
import os
import time
import atexit
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from orders import send_order_to_novaengel

# ====================== CONFIG ======================
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.getLogger('apscheduler').setLevel(logging.WARNING)
session = requests.Session()

# ====================== GESTION 429 ======================
def shopify_request(method, url, **kwargs):
    attempt = 0
    while True:
        time.sleep(0.7)
        try:
            r = session.request(method, url, **kwargs, timeout=30)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "8")
                wait = max(float(retry_after), 2) if retry_after else 8
                print(f"429 → attente {wait} secondes...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt >= 8:
                raise
            wait = 2 ** attempt
            print(f"Erreur réseau (tentative {attempt}/8) → attente {wait}s : {e}")
            time.sleep(wait)

# ====================== ROUTES ======================
@app.route("/sync")
def manual_sync():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync lancée"}), 200

@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify – AUTOMATIQUE TOUTES LES HEURES</h3>"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    try:
        order = request.get_json(force=True)
        result = send_order_to_novaengel(order)
        return jsonify({"status": "order sent to NovaEngel", "result": result}), 200
    except Exception as e:
        logging.exception("Erreur webhook commande")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    print("Démarrage…")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
