import requests
import os
import logging

# ================= CONFIG =================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
BASE_URL = "https://drop.novaengel.com/api"

# ================= LOGGER =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
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
def get_nova_products_stock():
    token = get_novaengel_token()
    r = requests.get(f"{BASE_URL}/stock/update/{token}", timeout=60)
    r.raise_for_status()
    return r.json()

def get_nova_products_full():
    token = get_novaengel_token()
    r = requests.get(f"{BASE_URL}/products/availables/{token}/fr", timeout=90)
    r.raise_for_status()
    return r.json()

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Commande Shopify reçue: {order.get('name')}")

    token = get_novaengel_token()
    nova_products = get_nova_products_full()

    # MAP EAN -> PRODUCT ID
    ean_to_product_id = {}
    for p in nova_products:
        for ean in p.get("EANs", []):
            ean_to_product_id[str(ean)] = p["Id"]

    lines = []
    for item in order.get("line_items", []):
        sku = str(item.get("sku")).strip()
        product_id = ean_to_product_id.get(sku)

        if not product_id:
            logger.warning(f"❌ SKU {sku} introuvable chez Nova Engel")
            continue

        lines.append({
            "productId": product_id,
            "units": int(item["quantity"])
        })

    if not lines:
        raise Exception("Aucun produit valide à envoyer à Nova Engel")

    shipping = order.get("shipping_address", {})

    order_payload = [{
        "orderNumber": order["name"].replace("#", "").replace("-", "")[:15],
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

    logger.info(f"📤 Payload Nova Engel: {order_payload}")

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=order_payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order['name']} envoyée à Nova Engel")
