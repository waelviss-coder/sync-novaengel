import requests
import os
import time

# =========================
# Credentials NovaEngel
# =========================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# =========================
# Obtenir le token NovaEngel
# =========================
def get_novaengel_token():
    print("🔑 Tentative d'obtenir le token NovaEngel...")
    try:
        r = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            timeout=90
        )
        r.raise_for_status()
        token = r.json().get("Token") or r.json().get("token")
        print(f"✅ Token reçu: {token[:6]}...")  # sécurité
        return token
    except requests.exceptions.RequestException as e:
        raise Exception(f"Impossible d'obtenir le token NovaEngel: {e}")

# =========================
# Envoyer une commande à NovaEngel
# =========================
def send_order_to_novaengel(order):
    print(f"📦 Nouvelle commande reçue pour traitement: {order.get('name')}")
    token = get_novaengel_token()

    # Mapping des items
    items = []
    for item in order.get("line_items", []):
        if item.get("sku"):
            items.append({
                "Reference": item["sku"],
                "Quantity": item["quantity"],
                "Price": item["price"]
            })
    if not items:
        raise Exception("Aucun item valide trouvé dans la commande")

    # Mapping de la commande
    payload = {
        "OrderNumber": order.get("name", f"TEST-{int(time.time())}"),
        "Date": order.get("created_at"),
        "Total": order.get("total_price"),
        "Currency": order.get("currency"),
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

    print(f"📤 Payload à envoyer à NovaEngel: {payload}")

    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=90
    )
    r.raise_for_status()
    print(f"✅ Commande {payload['OrderNumber']} envoyée à NovaEngel")
    print(f"💬 Réponse NovaEngel: {r.text}")
    return r.json()
