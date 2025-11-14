from flask import Flask, jsonify, request
import threading
import requests
import os

# === CONFIGURATION ===
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
SECRET_KEY = os.environ.get("SECRET_KEY", "pl0reals")

app = Flask(__name__)

# === 1) AUTOMATIC LOGIN NOVA ENGEL ===
def get_novaengel_token():
    url = "https://drop.novaengel.com/api/login"
    payload = {
        "user": NOVA_USER,
        "password": NOVA_PASS
    }

    r = requests.post(url, json=payload)
    print("🔍 Réponse brute Nova Engel :", r.text)
    r.raise_for_status()
    data = r.json()
    token = data.get("Token") or data.get("token")
    if not token:
        raise Exception(f"Réponse inattendue de Nova Engel : {data}")
    return token

# === 2) STOCK NOVA ENGEL ===
def get_novaengel_stock():
    print("🔄 Connexion à Nova Engel...")
    token = get_novaengel_token()
    print("🔄 Récupération du stock Nova Engel...")
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = requests.get(url)
    r.raise_for_status()
    stock_data = r.json()
    print(f"📦 {len(stock_data)} produits trouvés dans Nova Engel")
    return stock_data

# === SHOPIFY FUNCTIONS ===
def get_all_shopify_products():
    print("🔄 Récupération des produits Shopify...")
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
            url = extract_next_url(link_header)
        else:
            url = None

    print(f"🛍️ {len(all_products)} produits trouvés sur Shopify")
    return all_products

def extract_next_url(link_header):
    links = link_header.split(',')
    for link in links:
        if 'rel="next"' in link:
            return link.split(';')[0].strip('<> ')
    return None

def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    r = requests.get(url, headers=headers)
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
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return True

# === SYNC MAIN LOGIC ===
def sync_all_products():
    try:
        nova_stock_data = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_stock_map = {
            str(i.get("Id", "")).strip(): i.get("Stock", 0)
            for i in nova_stock_data if i.get("Id")
        }

        updated_count = 0

        for product in shopify_products:
            for variant in product["variants"]:
                sku = variant["sku"].strip().replace("'", "")
                if sku in nova_stock_map:
                    new_stock = nova_stock_map[sku]
                    old_stock = variant["inventory_quantity"]

                    if new_stock != old_stock:
                        update_shopify_stock(variant["inventory_item_id"], location_id, new_stock)
                        updated_count += 1
                        print(f"✅ {product['title']} (SKU {sku}) : {old_stock} → {new_stock}")

        print(f"📊 {updated_count} produits mis à jour")

    except Exception as e:
        print(f"❌ Erreur: {e}")

# === ROUTES ===
@app.route("/sync", methods=["GET"])
def run_sync():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "❌ Accès non autorisé"}), 403

    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "🚀 Synchronisation lancée"}), 200

@app.route("/admin-button", methods=["GET"])
def admin_button():
    return '''
        <h2>🔄 Synchronisation NovaEngel</h2>
        <button onclick="
            fetch('/sync?key=' + encodeURIComponent('{}'))
            .then(r => r.json())
            .then(j => alert(JSON.stringify(j)))
        ">
            Lancer la synchronisation
        </button>
    '''.format(SECRET_KEY)

@app.route("/", methods=["GET"])
def home():
    return "<h3>🚀 API Sync NovaEngel - Shopify</h3><p>Utilisez /sync?key=VOTRE_SECRET pour lancer la sync.</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
