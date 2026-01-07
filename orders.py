import requests
import os
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
BASE_URL = "https://drop.novaengel.com/api"

# ---------------- AUTH ----------------
def get_novaengel_token():
    r = requests.post(
        f"{BASE_URL}/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel manquant")
    return token

def digits_only(v):
    return re.sub(r"\D", "", str(v or ""))

# ---------------- SEND ORDER ----------------
def send_order_to_novaengel(order):
    token = get_novaengel_token()

    lines = []
    for item in order.get("line_items", []):
        product_id = digits_only(item.get("sku"))
        if not product_id:
            raise Exception("SKU (productId Nova Engel) manquant")

        lines.append({
            "productId": int(product_id),
            "units": int(item.get("quantity", 1))
        })

    if not lines:
        raise Exception("Aucune ligne valide")

    shipping = order.get("shipping_address") or {}

    payload = [{
        "orderNumber": digits_only(order.get("name"))[:15] or "1",
        "lines": lines,
        "name": shipping.get("first_name"),
        "secondName": shipping.get("last_name"),
        "street": shipping.get("address1"),
        "city": shipping.get("city"),
        "county": shipping.get("province", ""),
        "postalCode": shipping.get("zip"),
        "country": shipping.get("country"),
        "telephone": shipping.get("phone")
    }]

    logger.info(f"📤 Payload Nova Engel: {payload}")

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload,
        timeout=30
    )
    r.raise_for_status()

    logger.info("✅ Commande envoyée à Nova Engel")
    return r.json()