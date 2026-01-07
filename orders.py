import requests
import os
import re

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")
BASE_URL = "https://drop.novaengel.com/api"

def get_novaengel_token():
    r = requests.post(
        f"{BASE_URL}/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    return r.json()["Token"]

def clean_sku(sku):
    return re.sub(r"\D", "", str(sku or ""))

def send_order_to_novaengel(order):
    token = get_novaengel_token()

    lines = []
    for item in order.get("line_items", []):
        product_id = clean_sku(item.get("sku"))
        if not product_id:
            continue

        lines.append({
            "productId": int(product_id),
            "units": int(item.get("quantity", 1))
        })

    if not lines:
        raise Exception("Aucune ligne valide à envoyer")

    shipping = order.get("shipping_address") or {}

    payload = [{
        "orderNumber": clean_sku(order.get("name")) or "1",
        "lines": lines,
        "name": shipping.get("first_name"),
        "secondName": shipping.get("last_name"),
        "street": shipping.get("address1"),
        "city": shipping.get("city"),
        "postalCode": shipping.get("zip"),
        "country": shipping.get("country"),
        "telephone": shipping.get("phone")
    }]

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload,
        timeout=30
    )

    # 👉 LOG IMPORTANT POUR DEBUG
    print("Payload envoyé:", payload)
    print("Réponse Nova:", r.status_code, r.text)

    r.raise_for_status()
    return r.json()