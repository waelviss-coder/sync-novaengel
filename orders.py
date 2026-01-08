import requests
import os
import re

BASE_URL = "https://drop.novaengel.com/api"
USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]

def login():
    r = requests.post(f"{BASE_URL}/login", json={
        "user": USER,
        "password": PASS
    })
    r.raise_for_status()
    return r.json()["Token"]

def get_stock(token):
    r = requests.get(f"{BASE_URL}/stock/update/{token}")
    r.raise_for_status()
    return {str(p["Id"]): p["Stock"] for p in r.json()}

def numeric_order_number(name):
    return re.sub(r"\D", "", name)[-15:]

def send_order_to_novaengel(order):
    token = login()
    stock = get_stock(token)

    lines = []
    for item in order["line_items"]:
        sku = item.get("sku", "").replace("'", "").strip()
        if sku not in stock or stock[sku] <= 0:
            continue

        lines.append({
            "productId": int(sku),
            "units": int(item["quantity"])
        })

    if not lines:
        return {"status": "no valid items"}

    shipping = order["shipping_address"]

    payload = [{
        "orderNumber": numeric_order_number(order["name"]),
        "lines": lines,
        "name": shipping["first_name"],
        "secondName": shipping["last_name"],
        "street": shipping["address1"],
        "city": shipping["city"],
        "postalCode": shipping["zip"],
        "country": shipping["country_code"]
    }]

    r = requests.post(
        f"{BASE_URL}/orders/sendv2/{token}",
        json=payload
    )

    r.raise_for_status()
    return r.json()
