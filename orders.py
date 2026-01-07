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
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token")
    if not token:
        raise Exception("Nova Engel token missing")
    return token

# ================= UTILS =================
def clean_numeric(value):
    """Supprime tout sauf chiffres"""
    return re.sub(r"\D", "", str(value or ""))

def numeric_order_number(shopify_name):
    """
    Nova Engel exige un numéro NUMÉRIQUE (max 15)
    """
    return clean_numeric(shopify_name)[:15] or "1"

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Processing order {order.get('name')}")

    token = get_novaengel_token()

    items = []

    for item in order.get("line_items", []):
        # SKU = Id Nova Engel
        product_id = clean_numeric(item.get("sku"))

        if not product_id:
            raise Exception("SKU (Nova Engel Id) manquant")

        items.append({
            "productId": int(product_id),
            "units": item["quantity"]
        })

    if not items:
        raise Exception("Aucun produit valide dans la commande")

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

    logger.info(f"📤 Sending to Nova Engel: {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/orders/sendv2/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Order {order.get('name')} sent to Nova Engel")