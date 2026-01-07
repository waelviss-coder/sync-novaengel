import requests
import os
import logging

# ================= CONFIG =================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
BASE_URL = "https://drop.novaengel.com/api"

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================= AUTH =================
def get_novaengel_token():
    r = requests.post(
        f"{BASE_URL}/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=60
    )
    r.raise_for_status()

    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel non reçu")

    return token

# ================= PRODUCTS =================
def get_nova_products():
    token = get_novaengel_token()
    r = requests.get(
        f"{BASE_URL}/products/availables/{token}/fr",
        timeout=90
    )
    r.raise_for_status()
    return r.json()

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Commande Shopify reçue: {order.get('name')}")

    token = get_novaengel_token()
    products = get_nova_products()

    # MAP EAN -> PRODUCT ID
    ean_to_product_id = {}
    for p in products:
        for ean in p.get("EANs", []):
            ean_to_product_id[str(ean).strip()] = p["Id"]

    # BUILD ORDER LINES
    lines = []
    for item in order.get("line_items", []):
        sku = str(item.get("sku")).replace("'", "").strip()
        product_id = ean_to_product_id.get(sku)

        if not product_id:
            logger.error(f"❌ SKU {sku} introuvable chez Nova Engel")
            continue

        lines.append({
            "productId": product_id,
            "units": int(item.get("quantity", 1))
        })

    if not lines:
        raise Exception("Aucun produit valide à envoyer à Nova Engel")

    shipping = order.get("shipping_address") or {}

    # ORDER NUMBER NUMERIC (MAX 15)
    order_number = "".join(filter(str.isdigit, order.get("name", "")))[:15]

    if not order_number:
        raise Exception("orderNumber invalide (doit être numérique)")

    payload = [{
        "orderNumber": order_number,
        "carrierNotes": "Commande Shopify Plureals",
        "lines": lines,
        "name": shipping.get("first_name"),
        "secondName": shipping.get("last_name"),
        "telephone": shipping.get("phone", ""),
        "mobile": shipping.get("phone", ""),
        "street": shipping.get("address1"),
        "city": shipping.get("city"),
        "county": shipping.get("province", ""),
        "postalCode": shipping.get("zip"),
        "country": shipping.get("country_code")
    }]

    logger.info(f"📤 Payload envoyé à Nova Engel: {payload}")

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order_number} envoyée à Nova Engel")
