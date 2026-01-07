import requests
import os
import logging

# ================= LOGGER =================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(_name_)

# ================= CONFIG =================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ================= AUTH =================
def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={
            "user": NOVA_USER,
            "password": NOVA_PASS
        },
        timeout=60
    )
    r.raise_for_status()
    token = r.json().get("Token")
    if not token:
        raise Exception("Token Nova Engel manquant")
    return token

# ================= PRODUCTS =================
def get_novaengel_products(token):
    r = requests.get(
        f"https://drop.novaengel.com/api/stock/update/{token}",
        timeout=60
    )
    r.raise_for_status()
    return r.json()

# ================= SEND ORDER =================
def send_order_to_novaengel(order):
    logger.info(f"📦 Traitement commande {order.get('name')}")

    token = get_novaengel_token()
    products = get_novaengel_products(token)

    # 🔁 Mapping EAN -> Reference Nova Engel
    ean_to_reference = {
        str(p.get("EAN")).strip(): str(p.get("Reference")).strip()
        for p in products
        if p.get("EAN") and p.get("Reference")
    }

    items = []

    for item in order.get("line_items", []):
        # Shopify SKU = EAN dans ton cas
        raw_sku = item.get("sku", "")
        ean = raw_sku.replace("'", "").strip()

        if not ean:
            continue

        reference = ean_to_reference.get(ean)

        if not reference:
            raise Exception(f"EAN {ean} introuvable chez Nova Engel")

        items.append({
            "Reference": reference,
            "Quantity": item["quantity"],
            "Price": float(item["price"])
        })

    if not items:
        logger.warning("⚠ Aucun article valide → commande ignorée")
        return

    shipping = order.get("shipping_address") or {}

    payload = {
        "OrderNumber": order.get("name"),
        "Date": order.get("created_at"),
        "Total": float(order.get("total_price", 0)),
        "Currency": order.get("currency"),
        "Customer": {
            "FirstName": shipping.get("first_name"),
            "LastName": shipping.get("last_name"),
            "Address": shipping.get("address1"),
            "City": shipping.get("city"),
            "Zip": shipping.get("zip"),
            "Country": shipping.get("country"),
            "Phone": shipping.get("phone"),
            "Email": order.get("email")
        },
        "Items": items
    }

    logger.info(f"📤 Payload Nova Engel : {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order.get('name')} envoyée à Nova Engel")