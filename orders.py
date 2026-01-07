import requests
import os
import logging

# ================= CONFIG =================
BASE_URL = "https://drop.novaengel.com/api"
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ================= TOKEN =================
def get_novaengel_token():
    r = requests.post(
        f"{BASE_URL}/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel non reçu")
    return token

# ================= STOCK =================
def get_nova_stock():
    token = get_novaengel_token()
    r = requests.get(
        f"{BASE_URL}/stock/update/{token}",
        timeout=30
    )
    r.raise_for_status()
    return r.json()

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Commande Shopify: {order.get('name')}")

    token = get_novaengel_token()
    stock = get_nova_stock()

    # MAP : EAN (Shopify SKU) -> productId Nova Engel
    ean_to_product_id = {}
    for p in stock:
        if p.get("Id") and p.get("EAN"):
            ean_to_product_id[str(p["EAN"]).strip()] = p["Id"]

    lines = []
    for item in order.get("line_items", []):
        sku = str(item.get("sku")).replace("'", "").strip()
        product_id = ean_to_product_id.get(sku)

        if not product_id:
            logger.error(f"❌ Produit non trouvé chez Nova Engel : {sku}")
            continue

        lines.append({
            "productId": product_id,
            "units": int(item.get("quantity", 1))
        })

    if not lines:
        raise Exception("Aucun produit valide à envoyer")

    shipping = order.get("shipping_address", {})

    order_number = "".join(filter(str.isdigit, order.get("name", "")))[:15]
    if not order_number:
        raise Exception("orderNumber invalide")

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

    logger.info(f"📤 Envoi Nova Engel: {payload}")

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload,
        timeout=60
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order_number} envoyée à Nova Engel")
