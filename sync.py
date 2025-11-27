# sync.py
import requests
import os

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

def get_novaengel_token():
    r = requests.post("https://drop.novaengel.com/api/login",
                      json={"user": NOVA_USER, "password": NOVA_PASS})
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel manquant")
    return token

def get_novaengel_stock():
    token = get_novaengel_token()
    r = requests.get(f"https://drop.novaengel.com/api/stock/update/{token}")
    r.raise_for_status()
    return r.json()

def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}
    while url:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        products.extend(data["products"])
        link_header = r.headers.get("Link", "")
        url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")
    return products

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

def sync_all_products():
    modified = []
    try:
        nova_stock = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()
        nova_map = {str(i.get("Id","")).strip(): i.get("Stock",0) for i in nova_stock if i.get("Id")}

        for product in shopify_products:
            for variant in product["variants"]:
                sku = variant["sku"].strip().replace("'", "")
                if sku in nova_map:
                    old_stock = variant["inventory_quantity"]
                    new_stock = nova_map[sku]
                    if new_stock != old_stock:
                        update_shopify_stock(variant["inventory_item_id"], location_id, new_stock)
                        modified.append(f"{product['title']} | SKU {sku}: {old_stock} → {new_stock}")
        print(f"✅ Synchronisation terminée, produits modifiés:\n" + "\n".join(modified) if modified else "Aucun produit modifié")
    except Exception as e:
        print(f"❌ Erreur: {e}")

if __name__ == "__main__":
    sync_all_products()
