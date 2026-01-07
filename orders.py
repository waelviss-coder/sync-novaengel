import requests
import os

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ================= AUTH =================

def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token Nova Engel introuvable")
    return token

# ================= STOCK + PRICE =================

def get_novaengel_catalog(token):
    r = requests.get(
        f"https://drop.novaengel.com/api/stock/update/{token}",
        timeout=60
    )
    r.raise_for_status()

    catalog = {}
    for item in r.json():
        if not item.get("Id"):
            continue
        catalog[str(item["Id"]).strip()] = {
            "stock": int(item.get("Stock", 0)),
            "price": float(item.get("Price", 0))
        }
    return catalog

def clean_sku(sku):
    return sku.strip().replace("'", "").replace(" ", "") if sku else ""

# ================= SEND ORDER =================

def send_order_to_novaengel(order):
    token = get_novaengel_token()
    catalog = get_novaengel_catalog(token)

    items = []

    for item in order.get("line_items", []):
        sku = clean_sku(item.get("sku"))
        qty = int(item.get("quantity", 0))

        nova_item = catalog.get(sku)

        print("🧾 Shopify item:", sku, qty)

        if not nova_item:
            print(f"⛔ SKU {sku} absent chez Nova")
            continue

        if nova_item["stock"] <= 0:
            print(f"⛔ Stock Nova insuffisant pour {sku}")
            continue

        if qty <= 0:
            continue

        price = nova_item["price"]

        if price <= 0:
            print(f"⛔ Prix Nova invalide pour {sku}")
            continue

        items.append({
            "Id": sku,
            "Quantity": qty,
            "Price": price
        })

    if not items:
        return {"status": "no valid items sent"}

    shipping = order.get("shipping_address") or {}

    payload = {
        "OrderNumber": order.get("name", "TEST-UNKNOWN"),
        "Date": order.get("created_at"),
        "Currency": order.get("currency", "EUR"),
        "Total": round(sum(i["Price"] * i["Quantity"] for i in items), 2),
        "Customer": {
            "FirstName": shipping.get("first_name", ""),
            "LastName": shipping.get("last_name", ""),
            "Address": shipping.get("address1", ""),
            "City": shipping.get("city", ""),
            "Zip": shipping.get("zip", ""),
            "Country": shipping.get("country", ""),
            "Phone": shipping.get("phone", ""),
            "Email": order.get("email", "")
        },
        "Items": items
    }

    print("🚀 Payload Nova Engel:", payload)

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=30
    )

    print("📨 Réponse Nova:", r.status_code, r.text)
    r.raise_for_status()
    return r.json()
