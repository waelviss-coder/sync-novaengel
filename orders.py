import requests
import os

BASE_URL = "https://drop.novaengel.com/api"

def get_token():
    r = requests.post(
        f"{BASE_URL}/login",
        json={
            "user": os.environ["NOVA_USER"],
            "password": os.environ["NOVA_PASS"]
        }
    )
    r.raise_for_status()
    return r.json()["Token"]

def send_order_to_novaengel(order):
    token = get_token()

    lines = []
    for item in order["line_items"]:
        nova_id = item.get("sku")  # OU metafield

        if not nova_id:
            continue

        lines.append({
            "productId": int(nova_id),
            "units": int(item["quantity"])
        })

    if not lines:
        return {"status": "no valid items"}

    shipping = order["shipping_address"]

    payload = [{
        "orderNumber": order["id"],  # NUMERIQUE
        "carrierNotes": "Order from Shopify Plureals",
        "lines": lines,
        "name": shipping["first_name"],
        "secondName": shipping["last_name"],
        "telephone": shipping.get("phone", ""),
        "mobile": shipping.get("phone", ""),
        "street": shipping["address1"],
        "city": shipping["city"],
        "county": "",
        "postalCode": shipping["zip"],
        "country": shipping["country_code"]
    }]

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload
    )

    r.raise_for_status()
    return r.json()