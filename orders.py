import requests
import os
import time

# ===========================
# Credentials NovaEngel
# ===========================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# ===========================
# Obtenir le token NovaEngel
# ===========================
def get_novaengel_token():
    """
    Se connecte à NovaEngel pour obtenir un token d'authentification.
    Timeout augmenté à 90 secondes pour éviter les erreurs ReadTimeout.
    """
    r = requests.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=90
    )
    r.raise_for_status()
    return r.json().get("Token") or r.json().get("token")


# ===========================
# Envoyer une commande à NovaEngel
# ===========================
def send_order_to_novaengel(order):
    """
    Envoie la commande Shopify vers NovaEngel.
    Retry automatique 3 fois en cas de timeout.
    """

    token = get_novaengel_token()

    # Mapping des items
    items = []
    for item in order.get("line_items", []):
        if item.get("sku"):
            items.append({
                "Reference": item["sku"],  # SKU ou ProductId NovaEngel
                "Quantity": item["quantity"],
                "Price": item["price"]
            })

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

    # Retry automatique en cas de timeout
    for attempt in range(3):
        try:
            r = requests.post(
                f"https://drop.novaengel.com/api/order/create/{token}",
                json=payload,
                timeout=90  # timeout augmenté
            )
            r.raise_for_status()
            print(f"✅ Commande {payload['OrderNumber']} envoyée à NovaEngel")
            break
        except requests.exceptions.ReadTimeout:
            print(f"⚠ Timeout, nouvelle tentative {attempt+1}/3 dans 5s")
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors de l'envoi à NovaEngel: {e}")
            break

