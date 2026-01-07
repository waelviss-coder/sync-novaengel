import requests
import os
import logging

NOVA_BASE_URL = "https://drop.novaengel.com/api"
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
LANG = "fr"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
session = requests.Session()

# ---------------- LOGIN NOVA ENGEL ----------------
def get_novaengel_token():
    if not NOVA_USER or not NOVA_PASS:
        raise Exception(f"NOVA_USER ou NOVA_PASS non définis (NOVA_USER={NOVA_USER}, NOVA_PASS={'***' if NOVA_PASS else None})")
    r = session.post(f"{NOVA_BASE_URL}/login", json={"user": NOVA_USER, "password": NOVA_PASS}, timeout=30)
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception(f"Token Nova Engel non reçu. Response={r.text}")
    logging.info("🔑 Token Nova Engel obtenu")
    return token

# ---------------- GET STOCK ----------------
def get_novaengel_stock():
    token = get_novaengel_token()
    r = session.get(f"{NOVA_BASE_URL}/stock/update/{token}", timeout=60)
    r.raise_for_status()
    return r.json()

# ---------------- GET PRODUCT ID BY EAN ----------------
def get_product_id_by_ean(token, ean):
    r = session.get(f"{NOVA_BASE_URL}/products/availables/{token}/{LANG}", timeout=60)
    r.raise_for_status()
    for p in r.json():
        if str(p.get("EAN")) == str(ean):
            logging.info(f"✅ Produit trouvé → productId {p['Id']}")
            return p["Id"]
    raise Exception(f"EAN {ean} introuvable chez Nova Engel")

# ---------------- SEND ORDER ----------------
def send_order_to_novaengel(shopify_order):
    token = get_novaengel_token()
    lines = []

    for item in shopify_order.get("line_items", []):
        sku = str(item.get("sku","")).strip()
        qty = item.get("quantity", 0)
        if not sku or qty <= 0:
            continue
        logging.info(f"🔍 Recherche produit Nova Engel EAN: {sku}")
        product_id = get_product_id_by_ean(token, sku)
        lines.append({"productId": product_id, "units": qty})

    if not lines:
        raise Exception("Aucune ligne valide à envoyer")

    shipping = shopify_order.get("shipping_address", {})

    payload = [{
        "orderNumber": str(shopify_order.get("name")).replace("#",""),
        "carrierNotes": "Commande Shopify Plureals",
        "valoration": 0,
        "lines": lines,
        "name": shipping.get("first_name",""),
        "secondName": shipping.get("last_name",""),
        "telephone": shipping.get("phone",""),
        "mobile": shipping.get("phone",""),
        "street": shipping.get("address1",""),
        "city": shipping.get("city",""),
        "county": shipping.get("province",""),
        "postalCode": shipping.get("zip",""),
        "country": shipping.get("country_code","")
    }]

    logging.info(f"📤 Payload envoyé à Nova Engel: {payload}")
    r = session.post(f"{NOVA_BASE_URL}/orders/sendv2/{token}", json=payload, timeout=60)
    r.raise_for_status()
    logging.info(f"✅ Commande {payload[0]['orderNumber']} envoyée à Nova Engel")
    return r.json()
