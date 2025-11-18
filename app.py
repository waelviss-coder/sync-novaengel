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
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")  # Change ça sur Render !

app = Flask(__name__)
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Session simple SANS retry automatique (on gère nous-mêmes)
session = requests.Session()

# ====================== NOVA ENGEL ======================
def get_novaengel_token():
    url = "https://drop.novaengel.com/api/login"
    payload = {"user": NOVA_USER, "password": NOVA_PASS}
    r = session.post(url, json=payload, timeout=30)
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel non reçu")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

# ====================== SHOPIFY SAFE ======================
def shopify_request(method, url, **kwargs):
    """Fonction unique qui gère les 429 proprement"""
    for attempt in range(10):
        time.sleep(0.7)  # Respect du rate limit dès le départ
        r = session.request(method, url, **kwargs)
        if r.status_code == 429:
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.replace('.','').isdigit() else (2 ** attempt)
            print(f"Rate limit 429 → attente {wait} secondes...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise Exception("Trop de tentatives 429")

def get_all_shopify_products():
    all_products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    while url:
        r = shopify_request("GET", url, headers=headers, timeout=30)
        data = r.json()
        all_products.extend(data["products"])

        link_header = r.headers.get("Link", "")
        url = None
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip("<> ")
                    break
    return all_products

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    r = shopify_request("GET", url, headers=headers)
    return r.json()["locations"][0]["id"]

def update_shopify_stock(inventory_item_id, location_id, stock):
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": stock}
    shopify_request("POST", url, json=payload, headers=headers, timeout=30)

# ====================== SYNC PRINCIPALE ======================
def sync_all_products():
    print("\nDÉBUT SYNCHRONISATION AUTOMATIQUE")
    modified = 0
    try:
        nova_stock = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_map = {str(item.get("Id","")).strip(): item.get("Stock",0) for item in nova_stock if item.get("Id")}

        for product in shopify_products:
            for variant in product["variants"]:
                sku = variant["sku"].strip().replace("'", "")
                if sku in nova_map:
                    new_stock = nova_map[sku]
                    old_stock = variant["inventory_quantity"]
                    if new_stock != old_stock:
                        update_shopify_stock(variant["inventory_item_id"], location_id, new_stock)
                        print(f"MISE À JOUR → {product['title']} | SKU {sku} : {old_stock} → {new_stock}")
                        modified += 1

        print(f"SYNCHRONISATION TERMINÉE → {modified} produit(s) mis à jour\n" if modified else "Aucune modification.\n")
    except Exception as e:
        print(f"ERREUR : {e}\n")
        raise

# ====================== SCHÉDULER ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(func=sync_all_products, trigger="interval", minutes=60, id="auto_sync")
scheduler.start()

atexit.register(lambda: scheduler.shutdown(wait=False))
signal.signal(signal.SIGTERM, lambda s, f: scheduler.shutdown(wait=False))

# ====================== ROUTES ======================
@app.route("/sync", methods=["GET"])
def run_sync():
    if request.args.get("key") != SECRET_KEY:
        return jsonify({"error": "Accès refusé"}), 403
    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "Sync lancée"}), 200

@app.route("/admin-button")
def admin_button():
    return '''
    <div style="text-align:center;margin:50px;font-family:Arial;">
        <h2 style="color:#008060;">Synchronisation NovaEngel → Shopify</h2>
        <p style="font-size:18px;color:#555;">Automatique toutes les heures</p>
        <button onclick="fetch('/sync?key=pl0reals').then(r=>r.json()).then(d=>alert('Sync lancée !'))"
                style="background:#5c6ac4;color:white;padding:15px 30px;border:none;border-radius:8px;font-size:18px;cursor:pointer;">
            Lancer manuellement
        </button>
    </div>
    '''

@app.route("/")
def home():
    return "<h3>Sync NovaEngel - AUTOMATIQUE TOUTES LES HEURES</h3>"

# ====================== DÉMARRAGE ======================
if __name__ == "__main__":
    print("Démarrage - première sync dans 10 secondes...")
    time.sleep(10)
    threading.Thread(target=sync_all_products).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
