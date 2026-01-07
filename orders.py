import requests
import os
import logging
import re

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

# ================= CONFIG =================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
LANGUAGE = "en"

# ================= AUTH =================
def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token")
    if not token:
        raise Exception("Nova Engel token missing")
    return token

# ================= PRODUCTS =================
def get_novaengel_products(token):
    r = requests.get(
        f"https://drop.novaengel.com/api/products/availables/{token}/{LANGUAGE}",
        timeout=90
    )
    r.raise_for_status()
    return r.json()

# ================= UTILS =================
def normalize_ean(value: str) -> str:
    return value.replace("'", "").strip()

def numeric_order_number(shopify_name: str) -> str:
    """
    Nova Engel requires numeric orderNumber (max 15 chars)
    """
    digits = re.sub(r"\D", "", shopify_name)
    return digits[:15] or "1"

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Processing order {order.get('name')}")

    token = get_novaengel_token()
    products = get_novaengel_products(token)

    # 🔁 Build EAN → ProductId map
    ean_to_id = {}
    for p in products:
        for ean in p.get("EANs", []):
            ean_to_id[str(ean).strip()] = p["Id"]

    items = []

    for item in order.get("line_items", []):
        ean = normalize_ean(item.get("sku") or item.get("barcode") or "")
        if not ean:
            continue

        product_id = ean_to_id.get(ean)
        if not product_id:
            raise Exception(f"EAN {ean} introuvable chez Nova Engel")

        items.append({
            "productId": product_id,
            "units": item["quantity"]
        })

    if not items:
        logger.warning("⚠ No valid items → order ignored")
        return

    shipping = order.get("shipping_address") or {}

    payload = [{
        "orderNumber": numeric_order_number(order.get("name", "")),
        "name": shipping.get("first_name"),
        "secondName": shipping.get("last_name"),
        "street": shipping.get("address1"),
        "city": shipping.get("city"),
        "county": shipping.get("province"),
        "postalCode": shipping.get("zip"),
        "country": shipping.get("country_code"),
        "telephone": shipping.get("phone"),
        "lines": items
    }]

    logger.info(f"📤 Sending to Nova Engel: {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/orders/sendv2/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Order {order.get('name')} sent to Nova Engel")