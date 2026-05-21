import requests
import os
import time

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")


# ================= NOVA ENGEL =================
def get_novaengel_token():
    r = requests.post(
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
    r = requests.get(
        f"https://drop.novaengel.com/api/stock/update/{token}",
        timeout=60
    )
    r.raise_for_status()
    return r.json()


# ================= SHOPIFY =================
def shopify_request(method, url, **kwargs):
    attempt = 0
    while True:
        try:
            r = requests.request(method, url, **kwargs, timeout=30)

            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After", "5")
                wait = max(float(retry_after), 5)
                print(f"⚠️ 429 → attente {wait}s")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.RequestException as e:
            attempt += 1
            if attempt > 5:
                raise
            wait = 2 ** attempt
            print(f"⚠️ retry {attempt}/5 → {wait}s : {e}")
            time.sleep(wait)


def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    while url:
        r = shopify_request("GET", url, headers=headers)
        data = r.json()
        products.extend(data.get("products", []))

        url = None
        link_header = r.headers.get("Link", "")
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")

    return products


def get_shopify_location_id():
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/locations.json"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    r = shopify_request("GET", url, headers=headers)
    locations = r.json().get("locations", [])

    if not locations:
        raise Exception("Aucune location Shopify")

    return locations[0]["id"]


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
    time.sleep(0.1)


# ================= SYNC =================
def sync_all_products():
    modified = []

    try:
        nova_stock = get_novaengel_stock()
        shopify_products = get_all_shopify_products()
        location_id = get_shopify_location_id()

        nova_map = {
            str(i.get("Id", "")).strip(): i.get("Stock", 0)
            for i in nova_stock
            if i.get("Id")
        }

        nova_skus = set(nova_map.keys())

        print(f"📦 Nova SKUs: {len(nova_skus)}")
        print(f"🛍 Shopify products: {len(shopify_products)}")

        for product in shopify_products:
            for variant in product.get("variants", []):

                sku = (variant.get("sku") or "").strip().replace("'", "")
                if not sku:
                    continue

                inventory_item_id = variant["inventory_item_id"]
                old_stock = variant["inventory_quantity"]

                # =========================
                # 1. SKU EXISTE DANS NOVA → UPDATE STOCK
                # =========================
                if sku in nova_skus:
                    new_stock = nova_map.get(sku, 0)

                    if new_stock != old_stock:
                        update_shopify_stock(
                            inventory_item_id,
                            location_id,
                            new_stock
                        )

                        modified.append(
                            f"UPDATE | {product['title']} | {sku}: {old_stock} → {new_stock}"
                        )

                # =========================
                # 2. SKU NON NOVA
                # =========================
                else:
                    # 🚫 EXCEPTION: SKU "i"
                    if sku.startswith("i"):
                        continue

                    # désactivation (safe)
                    update_shopify_stock(
                        inventory_item_id,
                        location_id,
                        0
                    )

                    modified.append(
                        f"DISABLE | {product['title']} | {sku}"
                    )

        print("✅ Sync terminée")

        if modified:
            print("\n".join(modified))
        else:
            print("Aucun changement")

    except Exception as e:
        print(f"❌ Erreur sync: {e}")


if __name__ == "__main__":
    sync_all_products()
