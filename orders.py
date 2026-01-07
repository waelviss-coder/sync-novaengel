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

# ================= STOCK =================

def get_novaengel_stock_map(token):
    r = requests.get(
        f"https://drop.novaengel.com/api/stock/update/{token}",
        timeout=60
    )
    r.raise_for_status()

    return {
        str(item["Id"]).strip(): int(item.get("Stock", 0))
        for item in r.json() if item.get("Id")
    }

def clean_sku(sku):
    return sku.strip().replace("'", "").replace(" ", "") if sku else ""

# ================= SEND ORDER =================

def send_order_to_novaengel(order):
    token = get_novaengel_token()
    stock_map = get_novaengel_stock_map(token)

    items = []

    for item in order.get("line_items", []):
        sku = clean_sku(item.get("sku"))
        qty = int(item.get("quantity", 0))

        if not sku or qty <= 0:
            continue

        if sku not in stock_map:
            print(f"⛔ SKU {sku} absent chez Nova")
            continue

        if stock_map.get(sku, 0) <= 0:
            print(f"⛔ Stock Nova insuffisant pour {sku}")
            continue

        # 👉 PRIX SHOPIFY (OBLIGATOIRE)
        price = float(
            item.get("price")
            or item.get("price_set", {})
                .get("shop_money", {})
                .get("amount", 0)
        )

        if price <= 0:
            print(f"⛔ Prix Shopify invalide pour {sku}")
            continue

        print(f"✅ Item accepté : {sku} x{qty} @ {price}")

        items.append({
            "Id": sku,
            "Quantity": qty,
            "Price": price
        })

    if not items:
        return {"status": "no items sent"}

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

    print("🚀 Payload Nova Engel :", payload)

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=30
    )

    print("📨 Réponse Nova Engel :", r.status_code, r.text)
    r.raise_for_status()
    return r.json()
