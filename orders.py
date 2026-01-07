import requests
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ================= AUTH =================
def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={
            "user": NOVA_USER,
            "password": NOVA_PASS
        },
        timeout=30
    )
    r.raise_for_status()

    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel manquant")

    return token

# ================= UTILS =================
def only_digits(value):
    return re.sub(r"\D", "", str(value or ""))

def numeric_order_number(name):
    # Nova Engel: numérique, max 15 caractères
    return only_digits(name)[:15] or "1"

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Processing order {order.get('name')}")

    token = get_novaengel_token()

    items = []

    for item in order.get("line_items", []):
        # 🔴 SKU = ID Nova Engel (PAS EAN)
        product_id = only_digits(item.get("sku"))

        if not product_id:
            raise Exception("Variant SKU (productId Nova Engel) manquant")

        items.append({
            "productId": int(product_id),
            "units": int(item.get("quantity", 1))
        })

    if not items:
        raise Exception("Aucune ligne produit valide")

    shipping = order.get("shipping_address") or {}

    payload = [{
        "orderNumber": numeric_order_number(order.get("name")),
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

    logger.info(f"📤 Payload Nova Engel : {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/orders/sendv2/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Order {order.get('name')} sent to Nova Engel")