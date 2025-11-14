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
    payload = {"user": NOVA_USER, "password": NOVA_PASS}
    r = requests.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    token = data.get("Token") or data.get("token")
    if not token:
        raise Exception(f"Réponse inattendue de Nova Engel : {data}")
    return token

# === 2) STOCK NOVA ENGEL ===
def get_novaengel_stock():
    token = get_novaengel_token()
    url = f"https://drop.novaengel.com/api/stock/update/{token}"
    r = requests.get(url)
    r.raise_for_status()
    stock_data = r.json()
    return stock_data

# === SHOPIFY FUNCTIONS ===
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
            url = extract_next_url(link_header)
        else:
            url = None
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
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN, "Content-Type": "application/json"}
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": stock}
    r = requests.post(url, json=payload, headers=headers)
    r.raise_for_status()
    return True

# === SYNC MAIN LOGIC ===
def sync_all_products():
    modified_products = []
    try:
        nova_stock_data = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_stock_map = {
            str(i.get("Id", "")).strip(): i.get("Stock", 0)
            for i in nova_stock_data if i.get("Id")
        }

        for product in shopify_products:
            for variant in product["variants"]:
                sku = variant["sku"].strip().replace("'", "")
                if sku in nova_stock_map:
                    new_stock = nova_stock_map[sku]
                    old_stock = variant["inventory_quantity"]
                    if new_stock != old_stock:
                        update_shopify_stock(variant["inventory_item_id"], location_id, new_stock)
                        modified_products.append({
                            "title": product["title"],
                            "sku": sku,
                            "old_stock": old_stock,
                            "new_stock": new_stock
                        })
    except Exception as e:
        print(f"❌ Erreur: {e}")
    return modified_products

# === ROUTES ===
@app.route("/sync", methods=["GET"])
def run_sync():
    key = request.args.get("key")
    if key != SECRET_KEY:
        return jsonify({"error": "❌ Accès non autorisé"}), 403

    # Lancer la sync dans un thread et attendre la fin pour retourner les produits modifiés
    results = []
    def thread_func():
        nonlocal results
        results = sync_all_products()

    thread = threading.Thread(target=thread_func)
    thread.start()
    thread.join()  # attend que la sync se termine

    return jsonify({"status": "🚀 Synchronisation terminée", "products": results}), 200

@app.route("/admin-button")
def admin_button():
    return '''
    <div style="font-family:Arial,sans-serif; max-width:800px; margin:20px auto;">
        <h2 style="color:#008060;">🔄 Synchronisation NovaEngel</h2>
        <button id="syncBtn" style="
            background-color:#5c6ac4;
            color:white;
            border:none;
            padding:12px 24px;
            border-radius:6px;
            font-size:16px;
            cursor:pointer;
        ">
            Lancer la synchronisation
        </button>
        <div id="loader" style="display:none; margin-top:15px;">
            <p style="color:#555;">🔄 Synchronisation en cours...</p>
        </div>
        <div id="syncResults" style="margin-top:20px;"></div>
    </div>

    <script>
    const btn = document.getElementById("syncBtn");
    const loader = document.getElementById("loader");
    const resultsDiv = document.getElementById("syncResults");

    btn.onclick = () => {
        resultsDiv.innerHTML = "";
        loader.style.display = "block";
        fetch('/sync?key=pl0reals')
            .then(r => r.json())
            .then(data => {
                loader.style.display = "none";
                if(data.products && data.products.length > 0){
                    let html = "<h3 style='color:#008060;'>✅ Produits modifiés :</h3>";
                    data.products.forEach(p => {
                        html += `
                            <div style='border:1px solid #ddd; padding:10px; margin-bottom:5px; border-radius:4px;'>
                                <strong>${p.title}</strong> (SKU ${p.sku}): 
                                <span style='color:#c00;'>${p.old_stock}</span> → 
                                <span style='color:#008060;'>${p.new_stock}</span>
                            </div>
                        `;
                    });
                    resultsDiv.innerHTML = html;
                } else {
                    resultsDiv.innerHTML = "<p style='color:#555;'>Aucun produit n’a été modifié.</p>";
                }
            })
            .catch(err => {
                loader.style.display = "none";
                resultsDiv.innerHTML = "<p style='color:#c00;'>❌ Erreur lors de la synchronisation</p>";
                console.error(err);
            });
    }
    </script>
    '''

@app.route("/", methods=["GET"])
def home():
    return "<h3>🚀 API Sync NovaEngel - Shopify</h3><p>Utilisez /sync?key=VOTRE_SECRET pour lancer la sync.</p>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
