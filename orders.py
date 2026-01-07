import requests
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=60
    )
    r.raise_for_status()
    return r.json().get("Token")

def send_order_to_novaengel(order):
    token = get_novaengel_token()

    items = []
    for item in order.get("line_items", []):
        sku = item.get("sku")
        if not sku:
            continue

        items.append({
            "Reference": sku.strip(),
            "Quantity": item["quantity"],
            "Price": float(item["price"])
        })

    if not items:
        logger.warning("Commande sans SKU valide → ignorée")
        return

    shipping = order.get("shipping_address", {})

    payload = {
        "OrderNumber": order["name"],
        "Date": order["created_at"],
        "Total": float(order["total_price"]),
        "Currency": order["currency"],
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

    logger.info(f"📤 Envoi NovaEngel: {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()

    logger.info(f"✅ Commande {order['name']} envoyée à Nova Engel")