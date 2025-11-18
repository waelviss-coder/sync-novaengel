from flask import Flask, jsonify, request
import threading
import requests
import os
import time
import atexit
import signal
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ====================== CONFIGURATION ======================
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")  # Change cette valeur sur Render !

app = Flask(__name__)

# Désactive les logs verbeux d'APScheduler
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# Session requests avec retry automatique sur 429 et erreurs serveur
session = requests.Session()
retry = Retry(
    total=10,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST", "HEAD"]
)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# ====================== FONCTIONS NOVA ENGEL ======================
def get_novaengel_token():
    url = "https://drop.novaengel.com/api/login"
    payload = {"user": NOVA_USER, "password": NOVA_PASS}
    r = session.post(url, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    token = data.get("Token") or data.get("token")
    if not token:
        raise Exception(f"Token non reçu de NovaEngel : {data}")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

# ====================== FONCTIONS SHOPIFY (RATE LIMIT SAFE) ======================
def get_all_shopify_products():
    all_products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    while url:
        time.sleep(0.6)  # Respect strict du rate limit (moins de 2 req/s)
        r = session.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        all_products.extend(data["products"])

        link_header = r.headers.get('Link', '')
        url = None
        if 'rel="next"' in link_header:
            links = link_header.split(',')
            for link in links:
                if 'rel="next"' in link:
                    url = link.split(';')[0].strip('<> ')
                    break
    return all_products

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    time.sleep(0.6)
    r = session.get(url, headers=headers, timeout=30)
    r.raise_for_status()
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

    for attempt in range(6):
        r = session.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"Rate limit 429 → attente {wait} secondes (tentative {attempt + 1}/6)")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return True
    raise Exception("Échec mise à jour stock après 6 tentatives")

# ====================== SYNCHRONISATION PRINCIPALE ======================
def sync_all_products():
    print("\nDÉBUT DE LA SYNCHRONISATION AUTOMATIQUE")
    modified = 0
    try:
        nova_stock = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_map = {str(item.get("Id", "")).strip(): item.get("Stock", 0) for item in nova_stock if item.get("Id")}

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

        if modified == 0:
            print("Aucune modification détectée.")
        else:
            print(f"SYNCHRONISATION TERMINÉE → {modified} produit(s) mis à jour !\n")

    except Exception as e:
        print(f"ERREUR CRITIQUE : {e}\n")
        raise

# ====================== SCHÉDULER AUTO TOUTES LES 60 MIN ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(
    func=sync_all_products,
    trigger="interval",
    minutes=60,
    id="auto_sync_novaengel",
    replace_existing=True
)
scheduler.start()

# Nettoyage propre
atexit.register(lambda: scheduler.shutdown(wait=False))
def shutdown_handler(signum, frame):
    scheduler.shutdown(wait=False)
signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ====================== ROUTES FLASK ======================
@app.route("/sync", methods=["GET"])
def run_sync():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "Accès refusé"}), 403

    results = []
    def thread_func():
        nonlocal results
        results = sync_all_products()  # réutilise la même fonction safe
    thread = threading.Thread(target=thread_func)
    thread.start()
    thread.join()
    return jsonify({"status": "Synchronisation terminée", "modified": len(results)}), 200

@app.route("/admin-button")
def admin_button():
    return '''
    <div style="font-family:Arial,sans-serif; max-width:800px; margin:50px auto; text-align:center;">
        <h2 style="color:#008060;">Synchronisation NovaEngel → Shopify</h2>
        <p style="font-size:18px; color:#555;">
            Synchronisation automatique toutes les heures
        </p>
        <button onclick="fetch('/sync?key='+'pl0reals').then(r=>r.json()).then(d=>alert('Sync terminée ! '+(d.modified||0)+' produits mis à jour'))"
                style="background:#5c6ac4;color:white;padding:15px 30px;border:none;border-radius:8px;font-size:18px;cursor:pointer;margin:20px;">
            Lancer manuellement (optionnel)
        </button>
    </div>
    '''

@app.route("/")
def home():
    return "<h3>Sync NovaEngel → Shopify - AUTOMATIQUE TOUTES LES HEURES</h3>"

# ====================== DÉMARRAGE ======================
if __name__ == "__main__":
    print("Démarrage du service - première sync dans 5 secondes...")
    time.sleep(5)
    threading.Thread(target=sync_all_products).start()

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
