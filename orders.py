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

    # Préparer les items
    items = []
    for item in order.get("line_items", []):
        sku = item.get("sku")
        if not sku:
            continue  # ignorer si pas de SKU
        sku = sku.strip().replace("'", "")  # nettoyer les apostrophes
        price = float(item.get("price", 0))
        qty = int(item.get("quantity", 0))
        if qty <= 0:
            continue  # ignorer si quantité invalide
        items.append({
            "Id": sku,
            "Quantity": qty,
            "Price": price
        })

    # Infos client
    shipping = order.get("shipping_address") or {}
    payload = {
        "OrderNumber": order.get("name", "TEST-UNKNOWN"),
        "Date": order.get("created_at", "2026-01-07T12:00:00"),
        "Currency": order.get("currency", "EUR"),
        "Total": float(order.get("total_price", 0)),
        "Customer": {
            "FirstName": shipping.get("first_name", ""),
            "LastName": shipping.get("last_name", ""),
            "Address": shipping.get("address1", ""),
            "City": shipping.get("city", ""),
            "Zip": shipping.get("zip", ""),
            "Country": shipping.get("country", ""),
            "Phone": shipping.get("phone", ""),
            "Email": order.get("email", "")
        },
        "Items": items
    }

    # Envoyer la commande et loguer la réponse
    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=30
    )
    print("Nova Engel response:", r.status_code, r.text)
    r.raise_for_status()
    return r.json()
