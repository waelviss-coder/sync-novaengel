from flask import Flask, jsonify, request
import threading
import requests
import os

# === CONFIGURATION via variables d'environnement ===
SHOPIFY_STORE = "plureals.myshopify.com"
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_ENGEL_TOKEN = os.environ.get("NOVA_ENGEL_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY", "changemoi")  # clé pour sécuriser l'accès à /sync

app = Flask(__name__)

# === Fonctions existantes ===
def get_novaengel_stock():
    print("🔄 Récupération des stocks Nova Engel...")
    url = f"https://drop.novaengel.com/api/stock/update/{NOVA_ENGEL_TOKEN}"
    r = requests.get(url)
    r.raise_for_status()
    stock_data = r.json()
    print(f"📦 {len(stock_data)} produits trouvés dans Nova Engel")
    return stock_data

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

def sync_all_products():
    try:
        nova_stock_data = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_stock_map = {str(i.get("Id", "")).strip(): i.get("Stock", 0)
                          for i in nova_stock_data if i.get("Id")}
        print(f"🗂️ {len(nova_stock_map)} SKUs uniques dans Nova Engel")

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
        print(f"📊 {updated_count} produits mis à jour ✅")

    except Exception as e:
        print(f"❌ Erreur: {e}")

# === Routes web ===
@app.route("/sync", methods=["GET"])
def run_sync():
    # Sécurité avec clé
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "❌ Accès non autorisé"}), 403

    threading.Thread(target=sync_all_products).start()
    return jsonify({"status": "✅ Synchronisation lancée"}), 200

@app.route("/", methods=["GET"])
def home():
    return "<h3>🚀 API Sync NovaEngel - Shopify</h3><p>Utilisez /sync?key=VOTRE_SECRET pour lancer la mise à jour du stock.</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
