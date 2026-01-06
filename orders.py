import requests
import os

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

def get_novaengel_token():
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("Token") or r.json().get("token")

def send_order_to_novaengel(order):
    token = get_novaengel_token()

    items = []
    for item in order.get("line_items", []):
        if item.get("sku"):
            items.append({
                "Reference": item["sku"],
                "Quantity": item["quantity"],
                "Price": item["price"]
            })

    payload = {
        "OrderNumber": order["name"],
        "Date": order["created_at"],
        "Total": order["total_price"],
        "Currency": order["currency"],
        "Customer": {
            "FirstName": order["shipping_address"]["first_name"],
            "LastName": order["shipping_address"]["last_name"],
            "Address": order["shipping_address"]["address1"],
            "City": order["shipping_address"]["city"],
            "Zip": order["shipping_address"]["zip"],
            "Country": order["shipping_address"]["country"],
            "Phone": order["shipping_address"].get("phone"),
            "Email": order.get("email")
        },
        "Items": items
    }

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=60
    )
    r.raise_for_status()
