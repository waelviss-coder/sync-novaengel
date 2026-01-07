import requests
import logging
import os

# --------------------------------------------------
# CONFIG
# --------------------------------------------------
NOVA_BASE_URL = "https://drop.novaengel.com/api"
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASSWORD = os.environ.get("NOVA_PASSWORD")
LANG = "fr"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --------------------------------------------------
# LOGIN NOVA ENGEL
# --------------------------------------------------
def nova_login():
    url = f"{NOVA_BASE_URL}/login"
    payload = {
        "user": NOVA_USER,
        "password": NOVA_PASSWORD
    }

    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()

    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token Nova Engel non reçu")

    logging.info("🔑 Token Nova Engel obtenu")
    return token


# --------------------------------------------------
# GET PRODUCT ID BY EAN (SKU)
# --------------------------------------------------
def get_product_id_by_ean(token, ean):
    url = f"{NOVA_BASE_URL}/products/availables/{token}/{LANG}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()

    for p in r.json():
        if str(p.get("EAN")) == ean or ean in str(p.get("EAN", "")):
            logging.info(f"✅ Produit trouvé → productId {p['Id']}")
            return p["Id"]

    raise Exception(f"EAN {ean} introuvable chez Nova Engel")


# --------------------------------------------------
# SEND ORDER TO NOVA ENGEL
# --------------------------------------------------
def send_order_to_novaengel(shopify_order):
    token = nova_login()

    lines = []

    for item in shopify_order.get("line_items", []):
        sku = item.get("sku", "").replace("'", "").strip()
        qty = item.get("quantity", 0)

        if not sku or qty <= 0:
            continue

        logging.info(f"🔍 Recherche produit Nova Engel EAN: {sku}")
        product_id = get_product_id_by_ean(token, sku)

        lines.append({
            "productId": product_id,
            "units": qty
        })

    if not lines:
        raise Exception("Aucune ligne valide à envoyer")

    shipping = shopify_order.get("shipping_address", {})

    payload = [{
        "orderNumber": str(shopify_order.get("name")).replace("#", ""),
        "carrierNotes": "Commande Shopify Plureals",
        "valoration": 0,
        "lines": lines,
        "name": shipping.get("first_name", ""),
        "secondName": shipping.get("last_name", ""),
        "telephone": shipping.get("phone", ""),
        "mobile": shipping.get("phone", ""),
        "street": shipping.get("address1", ""),
        "city": shipping.get("city", ""),
        "county": shipping.get("province", ""),
        "postalCode": shipping.get("zip", ""),
        "country": shipping.get("country_code", "")
    }]

    logging.info(f"📤 Payload envoyé à Nova Engel: {payload}")

    url = f"{NOVA_BASE_URL}/orders/sendv2/{token}"
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()

    logging.info(f"✅ Commande {payload[0]['orderNumber']} envoyée à Nova Engel")
    return r.json()
