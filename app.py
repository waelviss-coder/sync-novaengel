from flask import Flask, jsonify, request
import threading
import requests
import os
import time
import atexit
import signal
import logging
from apscheduler.schedulers.background import BackgroundScheduler

# ====================== CONFIG ======================
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Session toute simple – ON NE MET PLUS JAMAIS DE RETRY AUTOMATIQUE
session = requests.Session()

# ====================== GESTION 429 MANUELLE (INFALLIBLE) ======================
def shopify_request(method, url, **kwargs):
    for attempt = 0
    while True:
        time.sleep(0.7)  # on reste très cool avec le rate limit
        try:
            r = session.request(method, url, **kwargs, timeout=30)
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                wait = 8 if not retry_after else max(float(retry_after), 2)
                print(f"429 détecté → attente {wait} secondes...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt >= 8:
                raise
            print(f"Erreur réseau (tentative {attempt}/8) → attente {2**attempt} sec : {e}")
            time.sleep(2 ** attempt)

# ====================== NOVA ENGEL ======================
def get_novaengel_token():
    url = "https://drop.novaengel.com/api/login"
    r = session.post(url, json={"user": NOVA_USER, "password": NOVA_PASS}, timeout=30)
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel manquant")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

# ====================== SHOPIFY ======================
def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    while url:
        r = shopify_request("GET", url, headers=headers)
        data = r.json()
        products.extend(data["products"])
        url = None
        for part in r.headers.get("Link", "").split(","):
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
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": stock}
    shopify_request("POST", url, json=payload, headers=headers)

# ====================== SYNC ======================
def sync_all_products():
    print("\nDÉBUT SYNCHRONISATION AUTOMATIQUE")
    try:
        nova = get_novaengel_stock()
        shopify = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_map = {str(item.get("Id","")).strip(): item.get("Stock",0) for item in nova if item.get("Id")}

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
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ====================== ROUTES ======================
@app.route("/sync", methods=["GET"])
def manual_sync():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "bad key"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "sync lancée"}), 200

@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify – AUTOMATIQUE TOUTES LES HEURES</h3>"

# ====================== START ======================
if __name__ == "__main__":
    print("Démarrage – première sync dans 10 secondes…")
    time.sleep(10)
    threading.Thread(target=sync_all_products).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
