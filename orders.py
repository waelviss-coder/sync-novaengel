import requests
import os
import re

BASE_URL = "https://drop.novaengel.com/api"
USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]


# =========================
# LOGIN NOVA
# =========================
def login():
    r = requests.post(f"{BASE_URL}/login", json={
        "user": USER,
        "password": PASS
    }, timeout=30)

    r.raise_for_status()

    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel introuvable")

    return token


# =========================
# STOCK NOVA
# =========================
def get_stock(token):
    r = requests.get(f"{BASE_URL}/stock/update/{token}", timeout=60)
    r.raise_for_status()

    data = r.json()

    # mapping SAFE
    return {
        str(p.get("Id")).strip(): int(p.get("Stock", 0))
        for p in data
        if p.get("Id") is not None
    }


# =========================
# ORDER NUMBER CLEAN
# =========================
def numeric_order_number(name):
    return re.sub(r"\D", "", str(name))[-15:]


# =========================
# SEND ORDER TO NOVA
# =========================
def send_order_to_novaengel(order):

    try:
        token = login()
        stock = get_stock(token)

        print("📦 STOCK KEYS SAMPLE:", list(stock.keys())[:10])

        lines = []

        for item in order.get("line_items", []):

            sku = (item.get("sku") or "").strip().replace("'", "")
            title = item.get("title", "unknown")

            print(f"🔎 ITEM: {sku} | {title}")

            # SKU vide → skip
            if not sku:
                print("⚠️ SKU vide ignoré")
                continue

            # SKU doit exister dans Nova stock
            if sku not in stock:
                print(f"❌ SKU inconnu dans Nova: {sku}")
                continue

            # stock check
            if stock[sku] <= 0:
                print(f"⚠️ Rupture stock Nova: {sku}")
                continue

            # IMPORTANT: productId = SKU (si Nova utilise Id string)
            lines.append({
                "productId": sku,
                "units": int(item.get("quantity", 1))
            })

        if not lines:
            print("❌ Aucun article valide pour Nova")
            return {"status": "no valid items"}

        shipping = order.get("shipping_address") or order.get("billing_address")

        if not shipping:
            raise Exception("Adresse manquante")

        payload = [{
            "orderNumber": numeric_order_number(order.get("name", "")),
            "lines": lines,
            "name": shipping.get("first_name", ""),
            "secondName": shipping.get("last_name", ""),
            "street": shipping.get("address1", ""),
            "city": shipping.get("city", ""),
            "postalCode": shipping.get("zip", ""),
            "country": shipping.get("country_code", "")
        }]

        print("🚀 PAYLOAD NOVA:", payload)

        r = requests.post(
            f"{BASE_URL}/orders/sendv2/{token}",
            json=payload,
            timeout=60
        )

        try:
            result = r.json()
        except:
            result = r.text

        print("📩 RESULT NOVA:", result)

        return result

    except Exception as e:
        print("❌ ERROR send_order_to_novaengel:", str(e))
        return {"status": "error", "message": str(e)}
