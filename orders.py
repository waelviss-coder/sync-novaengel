import requests
import logging
import os
import re

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
NOVA_BASE_URL = "https://drop.novaengel.com/api"
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASSWORD = os.environ.get("NOVA_PASSWORD")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

# --------------------------------------------------
# AUTH
# --------------------------------------------------
def nova_login():
    r = requests.post(
        f"{NOVA_BASE_URL}/login",
        json={
            "user": NOVA_USER,
            "password": NOVA_PASSWORD
        },
        timeout=20
    )
    r.raise_for_status()

    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel manquant")

    logger.info("🔑 Token Nova Engel obtenu")
    return token


# --------------------------------------------------
# UTILS
# --------------------------------------------------
def digits_only(value):
    """Supprime tout sauf les chiffres"""
    return re.sub(r"\D", "", str(value or ""))


# --------------------------------------------------
# SEND ORDER
# --------------------------------------------------
def send_order_to_novaengel(shopify_order):
    logger.info(f"📦 Traitement commande {shopify_order.get('name')}")

    token = nova_login()

    lines = []

    for item in shopify_order.get("line_items", []):
        # SKU Shopify = productId Nova Engel
        product_id = digits_only(item.get("sku"))
        quantity = int(item.get("quantity", 1))

        if not product_id:
            raise Exception("Variant SKU (productId Nova Engel) manquant")

        lines.append({
            "productId": int(product_id),
            "units": quantity
        })

    if not lines:
        raise Exception("Aucune ligne produit valide")

    shipping = shopify_order.get("shipping_address") or {}

    payload = [{
        "orderNumber": digits_only(shopify_order.get("name"))[:15] or "1",
        "lines": lines,
        "name": shipping.get("first_name"),
        "secondName": shipping.get("last_name"),
        "street": shipping.get("address1"),
        "city": shipping.get("city"),
        "county": shipping.get("province", ""),
        "postalCode": shipping.get("zip"),
        "country": shipping.get("country_code"),
        "telephone": shipping.get("phone")
    }]

    logger.info(f"📤 Envoi vers Nova Engel: {payload}")

    r = requests.post(
        f"{NOVA_BASE_URL}/orders/sendv2/{token}",
        json=payload,
        timeout=30
    )
    r.raise_for_status()

    logger.info("✅ Commande envoyée à Nova Engel")