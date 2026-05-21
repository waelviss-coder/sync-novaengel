import requests
import os
import time
import json

SHOPIFY_STORE = os.environ.get("SHOPIFY_STORE")
SHOPIFY_ACCESS_TOKEN = os.environ.get("SHOPIFY_ACCESS_TOKEN")
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

LOCK_FILE = "/tmp/shopify_sync_lock.json"


# ===================== SAFE RUN CONTROL =====================
def should_run_sync():
    try:
        if os.path.exists(LOCK_FILE):
            with open(LOCK_FILE, "r") as f:
                data = json.load(f)

            last_run = data.get("last_run", 0)
            now = time.time()

            # 10 min minimum entre runs (évite spam + doublons)
            if now - last_run < 600:
                print("⏭️ Sync trop récente → skip")
                return False

        return True

    except:
        return True


def save_last_run():
    with open(LOCK_FILE, "w") as f:
        json.dump({"last_run": time.time()}, f)


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


# ================= SHOPIFY REQUEST =================
def shopify_request(method, url, **kwargs):
    attempt = 0

    while True:
        try:
            r = requests.request(method, url, **kwargs, timeout=30)

            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 2))
                print(f"⚠️ 429 Shopify → wait {wait}s")
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except Exception as e:
            attempt += 1
            if attempt > 5:
                raise

            wait = 2 ** attempt
            print(f"⚠️ retry {attempt}/5 → {wait}s")
            time.sleep(wait)


# ================= SHOPIFY =================
def get_all_shopify_products():
    products = []
    url = f"https://{SHOPIFY_STORE}/admin/api/2024-10/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN}

    while url:
        r = shopify_request("GET", url, headers=headers)
        data = r.json()

        products.extend(data.get("products", []))

        url = None
        link = r.headers.get("Link", "")

        for part in link.split(","):
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


# ================= SYNC =================
def sync_all_products():
    modified = []

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

    count = 0

    for product in shopify_products:
        count += 1
        print(f"🔄 Product {count}/{len(shopify_products)}")

        for variant in product.get("variants", []):

            sku = (variant.get("sku") or "").strip().replace("'", "")
            if not sku:
                continue

            inventory_item_id = variant["inventory_item_id"]
            old_stock = variant.get("inventory_quantity", 0)

            # =====================
            # EXISTE DANS NOVA
            # =====================
            if sku in nova_skus:
                new_stock = nova_map.get(sku, 0)

                if new_stock == old_stock:
                    continue

                update_shopify_stock(inventory_item_id, location_id, new_stock)

                modified.append(
                    f"UPDATE | {product['title']} | {sku}: {old_stock} → {new_stock}"
                )

            # =====================
            # N'EXISTE PAS DANS NOVA
            # =====================
            else:
                if sku.startswith("i"):
                    continue

                if old_stock == 0:
                    continue

                update_shopify_stock(inventory_item_id, location_id, 0)

                modified.append(
                    f"DISABLE | {product['title']} | {sku}"
                )

    print("\n✅ SYNC TERMINÉE")

    if modified:
        print("\n".join(modified))
    else:
        print("Aucun changement")


# ================= MAIN =================
if __name__ == "__main__":
    if should_run_sync():
        try:
            sync_all_products()
        finally:
            save_last_run()
    else:
        print("⏭️ Sync ignorée (lock actif)")
