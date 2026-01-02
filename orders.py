import requests
import os

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

SESSION = requests.Session()


def get_novaengel_token():
    r = SESSION.post(
        "https://drop.novaengel.com/api/login",
        json={"user": NOVA_USER, "password": NOVA_PASS},
        timeout=30
    )
    r.raise_for_status()
    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Token NovaEngel manquant")
    return token


def send_order_to_novaengel(order):
    token = get_novaengel_token()

    products = []
    for item in order.get("line_items", []):
        if item.get("sku"):
            products.append({
                "Id": item["sku"].strip(),
                "Qte": item["quantity"]
            })

    if not products:
        raise Exception("Aucun produit valide à envoyer")

    shipping = order.get("shipping_address", {})

    payload = {
        "Client": shipping.get("name", "Client Shopify"),
        "Telephone": shipping.get("phone", ""),
        "Adresse": shipping.get("address1", ""),
        "Ville": shipping.get("city", ""),
        "Produits": products
    }

    r = SESSION.post(
        f"https://drop.novaengel.com/api/order/add/{token}",
        json=payload,
        timeout=60
    )
    r.raise_for_status()
