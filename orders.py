import requests
import logging
import os

NOVA_BASE_URL = "https://drop.novaengel.com/api"
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASSWORD = os.environ.get("NOVA_PASSWORD")
LANG = "fr"

# --------------------------------------------------
# LOGIN
# --------------------------------------------------
def nova_login():
    url = f"{NOVA_BASE_URL}/login"
    payload = {
        "user": NOVA_USER,
        "password": NOVA_PASSWORD
    }

    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

    token = r.json().get("Token")
    if not token:
        raise Exception("❌ Token Nova Engel non reçu")

    logging.info("🔑 Token Nova Engel obtenu")
    return token


# --------------------------------------------------
# GET PRODUCT ID BY EAN
# --------------------------------------------------
def get_product_id_by_ean(token, ean):
    url = f"{NOVA_BASE_URL}/products/availables/{token}/{LANG}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    products = r.json()
    logging.info(f"📊 {len(products)} produits analysés")

    for p in products:
        eans = p.get("EANs", [])
        if ean in eans:
            logging.info(f"✅ EAN trouvé → productId {p['Id']}")
            return p["Id"]

    logging.error(f"❌ EAN non trouvé dans Nova Engel: {ean}")
    return None


# --------------------------------------------------
# SEND ORDER TO NOVA ENGEL
# --------------------------------------------------
def send_order_to_novaengel(shopify_order):
    token = nova_login()

    lines = []

    for item in shopify_order["line_items"]:
        ean = item["sku"].strip()
        qty = item["quantity"]

        logging.info(f"🔍 Recherche EAN NovaEngel: {ean}")

        product_id = get_product_id_by_ean(token, ean)
        if not product_id:
            raise Exception(f"EAN {ean} introuvable chez Nova Engel")

        lines.append({
            "productId": product_id,
            "units": qty
        })

    shipping = shopify_order["shipping_address"]

    order_payload = [{
        "orderNumber": str(shopify_order["name"]).replace("#", "").zfill(10),
        "carrierNotes": "",
        "valoration": 0,
        "lines": lines,
        "name": shipping["first_name"],
        "secondName": shipping["last_name"],
        "telephone": "",
        "mobile": "",
        "street": shipping["address1"],
        "city": shipping["city"],
        "county": shipping.get("province", ""),
        "postalCode": shipping["zip"],
        "country": shipping["country_code"]
    }]

    url = f"{NOVA_BASE_URL}/orders/sendv2/{token}"
    r = requests.post(url, json=order_payload, timeout=30)
    r.raise_for_status()

    logging.info("✅ Commande envoyée à Nova Engel")
    return r.json()
