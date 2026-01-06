import requests
import os
import logging

# ================= CONFIG =================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ================= LOGGER =================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ================= TOKEN =================
def get_novaengel_token():
    try:
        r = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("Token")
    except Exception as e:
        logger.error(f"❌ Token error: {e}")
    return None

# ================= EAN → PRODUCT ID (STOCK) =================
def get_product_id_by_ean(ean, token):
    ean = str(ean).strip().replace("'", "")
    logger.info(f"🔍 Recherche EAN NovaEngel: {ean}")

    url = f"https://drop.novaengel.com/api/stocks/{token}"
    r = requests.get(url, timeout=30)

    if r.status_code != 200:
        logger.error(f"❌ Stock API error {r.status_code}")
        return None

    for item in r.json():
        if str(item.get("EAN")) == ean:
            product_id = item.get("ProductId")
            logger.info(f"✅ EAN trouvé → ProductId {product_id}")
            return product_id

    logger.error(f"❌ EAN non trouvé dans le stock: {ean}")
    return None

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info("🚀 Envoi commande NovaEngel")

    token = get_novaengel_token()
    if not token:
        return False

    lines = []
    for item in order.get("line_items", []):
        ean = item.get("sku")
        qty = int(item.get("quantity", 1))

        if not ean:
            continue

        product_id = get_product_id_by_ean(ean, token)
        if not product_id:
            return False

        lines.append({
            "productId": product_id,
            "units": qty
        })

    if not lines:
        logger.error("❌ Aucun produit valide")
        return False

    shipping = order.get("shipping_address", {})
    phone = ''.join(filter(str.isdigit, shipping.get("phone", ""))) or "600000000"

    payload = [{
        "orderNumber": order.get("name", "").replace("#", "")[:15],
        "carrierNotes": f"Shopify {order.get('name')}",
        "lines": lines,
        "name": shipping.get("first_name", "Client")[:50],
        "secondName": shipping.get("last_name", "")[:50],
        "telephone": phone[:15],
        "mobile": phone[:15],
        "street": shipping.get("address1", "Adresse")[:100],
        "city": shipping.get("city", "Ville")[:50],
        "postalCode": shipping.get("zip", "00000")[:10],
        "country": (shipping.get("country_code") or "ES")[:2]
    }]

    url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
    r = requests.post(url, json=payload, timeout=30)

    logger.info(f"📥 HTTP {r.status_code}")

    if r.status_code == 200:
        result = r.json()[0]
        if result.get("Errors"):
            for e in result["Errors"]:
                logger.error(f"❌ NovaEngel error: {e}")
            return False

        logger.info(f"🎉 Commande acceptée: {result}")
        return True

    logger.error(r.text[:200])
    return False
