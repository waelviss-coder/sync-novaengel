import requests
import os
import re
import logging

BASE_URL = "https://drop.novaengel.com/api"
USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]

logging.basicConfig(level=logging.INFO)


# =========================
# LOGIN
# =========================
def login():
    r = requests.post(f"{BASE_URL}/login", json={
        "user": USER,
        "password": PASS
    }, timeout=30)

    r.raise_for_status()

    token = r.json().get("Token") or r.json().get("token")

    if not token:
        raise Exception("Token Nova introuvable")

    return token


# =========================
# STOCK
# =========================
def get_stock(token):
    r = requests.get(f"{BASE_URL}/stock/update/{token}", timeout=60)
    r.raise_for_status()

    data = r.json()

    stock_map = {}

    for p in data:
        pid = p.get("Id")
        if not pid:
            continue

        stock_map[str(pid).strip()] = int(p.get("Stock", 0))

    logging.info(f"📦 Nova stock loaded: {len(stock_map)} items")

    return stock_map


# =========================
# ORDER NUMBER CLEAN
# =========================
def numeric_order_number(name):
    return re.sub(r"\D", "", str(name))[-15:]


# =========================
# CORE FUNCTION
# =========================
def send_order_to_novaengel(order):

    token = login()
    stock = get_stock(token)

    lines = []

    logging.info(f"📦 Processing order {order.get('name')}")

    for item in order.get("line_items", []):

        sku = (item.get("sku") or "").strip()

        # ❌ ignore invalid lines
        if not sku:
            logging.warning(f"⚠️ SKU vide ignoré: {item.get('title')}")
            continue

        # ❌ skip non-product items (plans, warranties, etc.)
        if not item.get("product_exists", True):
            logging.warning(f"⚠️ Produit non physique ignoré: {sku}")
            continue

        # ❌ check stock existence
        if sku not in stock:
            logging.warning(f"❌ SKU inconnu Nova: {sku}")
            continue

        # ❌ stock check
        if stock[sku] <= 0:
            logging.warning(f"⚠️ Rupture stock Nova: {sku}")
            continue

        lines.append({
            "productId": int(sku),
            "units": int(item.get("quantity", 1))
        })

    if not lines:
        logging.error("❌ Aucun produit valide pour Nova")
        return {
            "status": "failed",
            "reason": "no valid items"
        }

    shipping = order.get("shipping_address") or order.get("billing_address")

    if not shipping:
        logging.error("❌ Adresse manquante")
        return {"status": "error", "reason": "missing address"}

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

    logging.info(f"🚀 Sending payload to Nova: {payload}")

    try:
        r = requests.post(
            f"{BASE_URL}/orders/sendv2/{token}",
            json=payload,
            timeout=60
        )

        result = r.json()
        logging.info(f"📩 Nova response: {result}")

        # ❗ IMPORTANT: detect real failure
        if isinstance(result, list) and result[0].get("Message") == "KO":
            logging.error(f"❌ Nova rejected order: {result}")
            return {
                "status": "rejected",
                "nova_error": result
            }

        return {
            "status": "success",
            "nova": result
        }

    except Exception as e:
        logging.exception("❌ Error sending to Nova")
        return {
            "status": "error",
            "message": str(e)
        }
