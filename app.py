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
                try:
                    wait = max(float(retry_after), 2)
                except:
                    wait = 8
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

# ====================== NOVA ENGEL STOCK ======================
def get_novaengel_token():
    from orders import NOVA_USER, NOVA_PASS
    r = session.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel manquant")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    r = session.get(f"https://drop.novaengel.com/api/stock/update/{token}", timeout=60)
    r.raise_for_status()
    return r.json()

# ====================== SHOPIFY ======================
def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    while url:
        r = shopify_request("GET", url, headers=headers)
        products.extend(r.json()["products"])
        url = None
        link = r.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")
                break
    return products

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    r = shopify_request("GET", url, headers={"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN})
    return r.json()["locations"][0]["id"]

def update_shopify_stock(inventory_item_id, location_id, stock):
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": stock
    }
    shopify_request("POST", url, json=payload, headers=headers)

# ====================== SYNC ======================
def sync_all_products():
    print("\nDÉBUT SYNCHRONISATION AUTOMATIQUE")
    try:
        nova = get_novaengel_stock()
        shopify = get_all_shopify_products()
        location_id = get_shopify_location_id()
        nova_map = {str(item.get("Id","")).strip().replace("'", ""): item.get("Stock",0) for item in nova if item.get("Id")}
        modified = 0

        for product in shopify:
            for variant in product["variants"]:
                sku = variant["sku"].strip().replace("'", "")
                if sku in nova_map and nova_map[sku] != variant["inventory_quantity"]:
                    update_shopify_stock(variant["inventory_item_id"], location_id, nova_map[sku])
                    print(f"MISE À JOUR → {product['title']} | SKU {sku} : {variant['inventory_quantity']} → {nova_map[sku]}")
                    modified += 1

        print(f"SYNCHRONISATION TERMINÉE → {modified} produit(s) mis à jour\n" if modified else "Aucune modification\n")
    except Exception as e:
        print(f"ERREUR FATALE : {e}\n")
        raise

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="sync_job")
scheduler.start()
atexit.register(lambda: scheduler.shutdown(wait=False))

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
        send_order_to_novaengel(order)  # <-- SKU nettoyé et prix géré
        return jsonify({"status": "order sent to NovaEngel"}), 200
    except Exception as e:
        logging.exception("Erreur webhook commande")
        return jsonify({"error": str(e)}), 500

# ====================== START ======================
if __name__ == "__main__":
    print("Démarrage – première sync dans 10 secondes…")
    time.sleep(10)
    threading.Thread(target=sync_all_products).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
