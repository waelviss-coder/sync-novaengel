from flask import Flask, request, jsonify
import threading
import time
import logging
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
import os
import requests

# ====================== CONFIG ======================
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")
SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE", "plureals.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASSWORD = os.environ.get("NOVA_PASSWORD")
NOVA_BASE_URL = "https://drop.novaengel.com/api"
LANG = "fr"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger('apscheduler').setLevel(logging.WARNING)
session = requests.Session()

# ====================== NOVA ENGEL ======================
def nova_login():
    url = f"{NOVA_BASE_URL}/login"
    payload = {"user": NOVA_USER, "password": NOVA_PASSWORD}
    r = session.post(url, json=payload, timeout=30)
    r.raise_for_status()

    logging.info(f"Response Nova Engel login: {r.text}")  # debug

    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token Nova Engel non reçu")
    logging.info("🔑 Token Nova Engel obtenu")
    return token

def get_product_id_by_ean(token, ean):
    url = f"{NOVA_BASE_URL}/products/availables/{token}/{LANG}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    for p in r.json():
        if str(p.get("EAN")) == ean or ean in str(p.get("EAN", "")):
            logging.info(f"✅ Produit trouvé → productId {p['Id']}")
            return p["Id"]
    raise Exception(f"EAN {ean} introuvable chez Nova Engel")

def send_order_to_novaengel(shopify_order):
    token = nova_login()
    lines = []
    for item in shopify_order.get("line_items", []):
        sku = item.get("sku", "").replace("'", "").strip()
        qty = item.get("quantity", 0)
        if not sku or qty <= 0:
            continue
        logging.info(f"🔍 Recherche produit Nova Engel EAN: {sku}")
        product_id = get_product_id_by_ean(token, sku)
        lines.append({"productId": product_id, "units": qty})

    if not lines:
        raise Exception("Aucune ligne valide à envoyer")

    shipping = shopify_order.get("shipping_address", {})
    payload = [{
        "orderNumber": str(shopify_order.get("name")).replace("#", ""),
        "carrierNotes": "Commande Shopify Plureals",
        "valoration": 0,
        "lines": lines,
        "name": shipping.get("first_name", ""),
        "secondName": shipping.get("last_name", ""),
        "telephone": shipping.get("phone", ""),
        "mobile": shipping.get("phone", ""),
        "street": shipping.get("address1", ""),
        "city": shipping.get("city", ""),
        "county": shipping.get("province", ""),
        "postalCode": shipping.get("zip", ""),
        "country": shipping.get("country_code", "")
    }]

    logging.info(f"📤 Payload envoyé à Nova Engel: {payload}")
    url = f"{NOVA_BASE_URL}/orders/sendv2/{token}"
    r = session.post(url, json=payload, timeout=60)
    r.raise_for_status()
    logging.info(f"✅ Commande {payload[0]['orderNumber']} envoyée à Nova Engel")
    return r.json()

# ====================== SYNC ======================
def sync_all_products():
    print("\nDÉBUT SYNCHRONISATION AUTOMATIQUE")
    try:
        # Ici mettre ton code complet Nova Engel → Shopify
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
