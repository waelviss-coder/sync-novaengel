from flask import Flask, jsonify, request
import threading
import requests
import os
import atexit
import signal
import logging
from apscheduler.schedulers.background import BackgroundScheduler

# === CONFIGURATION ===
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")  # tu peux changer cette valeur

app = Flask(__name__)

# Pour éviter les logs inutiles du scheduler
logging.getLogger('apscheduler').setLevel(logging.WARNING)

# ====================== TES FONCTIONS EXISTANTES (à garder telles quelles) ======================
def get_novaengel_token():
    url = "https://drop.novaengel.com/api/login"
    payload = {"user": NOVA_USER, "password": NOVA_PASS}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    token = data.get("Token") or data.get("token")
    if not token:
        raise Exception(f"Réponse inattendue de Nova Engel : {data}")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def get_all_shopify_products():
    all_products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    while url:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        all_products.extend(data["products"])
        link_header = r.headers.get('Link', '')
        if 'rel="next"' in link_header:
            links = link_header.split(',')
            for link in links:
                if 'rel="next"' in link:
                    url = link.split(';')[0].strip('<> ')
                    break
            else:
                url = None
        else:
            url = None
    return all_products

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()["locations"][0]["id"]

def update_shopify_stock(inventory_item_id, location_id, stock):
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/inventory_levels/set.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": stock}
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return True

# ====================== FONCTION DE SYNCHRO (avec logs) ======================
def sync_all_products():
    print("DÉBUT SYNCHRONISATION AUTOMATIQUE")
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
            print(f"SYNCHRONISATION TERMINÉE → {modified} produit(s) mis à jour")
    except Exception as e:
        print(f"ERREUR CRITIQUE : {e}")
        raise

# ====================== SCHÉDULER AUTOMATIQUE TOUTES LES HEURES ======================
scheduler = BackgroundScheduler(timezone="Europe/Paris")
scheduler.add_job(
    func=sync_all_products,
    trigger="interval",
    minutes=60,
    id="auto_sync_novaengel",
    replace_existing=True
)
scheduler.start()

# Nettoyage propre à l'arrêt
atexit.register(lambda: scheduler.shutdown(wait=False))

def shutdown_handler(signum, frame):
    print("Arrêt du scheduler...")
    scheduler.shutdown(wait=False)

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ====================== ROUTES (inchangées) ======================
@app.route("/sync", methods=["GET"])
def run_sync():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "Accès refusé"}), 403
    
    results = []
    def thread_func():
        nonlocal results
        results = sync_all_products()
    threading.Thread(target=thread_func).start()
    threading.Thread(target=thread_func).join()
    return jsonify({"status": "Synchronisation terminée", "products": results}), 200

@app.route("/admin-button")
def admin_button():
    return '''
    <div style="font-family:Arial,sans-serif; max-width:800px; margin:40px auto; text-align:center;">
        <h2 style="color:#008060;">Synchronisation NovaEngel → Shopify</h2>
        <p>Sync automatique toutes les heures activée</p>
        <button onclick="fetch('/sync?key='+'pl0reals').then(r=>r.json()).then(d=>alert('Sync terminée ! '+d.products.length+' produits modifiés'))" 
                style="background:#5c6ac4;color:white;padding:15px 30px;border:none;border-radius:8px;font-size:18px;cursor:pointer;">
            Lancer manuellement (optionnel)
        </button>
    </div>
    '''

@app.route("/")
def home():
    return "<h3>API Sync NovaEngel - AUTOMATIQUE TOUTES LES HEURES</h3>"

if __name__ == "__main__":
    # Première sync immédiate au démarrage
    print("Lancement de la première synchronisation au démarrage...")
    threading.Thread(target=sync_all_products).start()
    
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
