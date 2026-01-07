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
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Impossible d'obtenir le token Nova Engel")
    return token


def send_order_to_novaengel(order):
    """
    Envoie une commande Shopify à Nova Engel
    en utilisant le Variant SKU Shopify comme Id Nova Engel
    """
    token = get_novaengel_token()

    # Préparer les items pour Nova Engel
    items = []
    for item in order.get("line_items", []):
        sku = item.get("sku")
        if not sku:
            continue  # ignorer si pas de SKU
        items.append({
            "Id": sku.strip(),           # <-- Ici on utilise l'ID Nova Engel = SKU Shopify
            "Quantity": item["quantity"],
            "Price": float(item["price"])
        })

    # Préparer la commande complète
    shipping = order.get("shipping_address") or {}
    payload = {
        "OrderNumber": order["name"],
        "Date": order["created_at"],
        "Currency": order["currency"],
        "Total": float(order["total_price"]),
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

    # Envoyer la commande à Nova Engel
    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=30
    )
    r.raise_for_status()
    return r.json()
