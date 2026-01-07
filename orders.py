import requests
import os
import logging

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
    return r.json().get("Token")

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

    # 🔁 Mapping EAN -> Id Nova Engel
    ean_to_id = {
        str(p.get("EAN")).strip(): p.get("Id")
        for p in products
        if p.get("EAN") and p.get("Id")
    }

    items = []

    for item in order.get("line_items", []):
        # Shopify SKU contient l’EAN
        ean = (item.get("sku") or "").replace("'", "").strip()

        if not ean:
            continue

        nova_id = ean_to_id.get(ean)

        if not nova_id:
            raise Exception(f"EAN {ean} introuvable chez Nova Engel")

        items.append({
            "Id": nova_id,
            "Quantity": item["quantity"],
            "Price": float(item["price"])
        })

    if not items:
        logger.warning("⚠ Aucun produit valide → commande ignorée")
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

    logger.info(f"📤 Envoi Nova Engel : {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order.get('name')} envoyée à Nova Engel")