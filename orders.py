import requests
import os

NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

def get_novaengel_token():
    """Récupère le token Nova Engel"""
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

def get_novaengel_stock_map():
    """
    Retourne un dictionnaire {Id: Stock} pour vérifier si un SKU existe
    """
    token = get_novaengel_token()
    r = requests.get(f"https://drop.novaengel.com/api/stock/update/{token}", timeout=60)
    r.raise_for_status()
    stock = r.json()
    stock_map = {str(item.get("Id","")).strip(): item.get("Stock",0) for item in stock if item.get("Id")}
    return stock_map, token

def clean_sku(sku):
    """Nettoie le SKU pour correspondre à l'Id Nova Engel"""
    if not sku:
        return ""
    return sku.strip().lstrip("'").replace("'", "").replace(" ", "")

def send_order_to_novaengel(order):
    """
    Envoie une commande Shopify à Nova Engel
    en utilisant le Variant SKU Shopify comme Id Nova Engel
    """
    stock_map, token = get_novaengel_stock_map()

    # Préparer les items
    items = []
    for item in order.get("line_items", []):
        sku = clean_sku(item.get("sku"))
        if not sku:
            continue
        if sku not in stock_map:
            print(f"⚠ SKU {sku} non trouvé dans Nova Engel, ignoré")
            continue
        price = float(item.get("price", 0))
        qty = int(item.get("quantity", 0))
        if qty <= 0 or price <= 0:
            continue
        items.append({
            "Id": sku,
            "Quantity": qty,
            "Price": price
        })

    if not items:
        print("⚠ Aucun item valide à envoyer → commande ignorée")
        return {"status": "no items sent"}

    shipping = order.get("shipping_address") or {}
    payload = {
        "OrderNumber": order.get("name", "TEST-UNKNOWN"),
        "Date": order.get("created_at", "2026-01-07T12:00:00"),
        "Currency": order.get("currency", "EUR"),
        "Total": float(order.get("total_price", sum(i["Price"]*i["Quantity"] for i in items))),
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

    # Envoi
    r = requests.post(
        f"https://drop.novaengel.com/api/order/create/{token}",
        json=payload,
        timeout=30
    )
    print("Payload envoyé à Nova Engel:", payload)
    print("Réponse Nova Engel:", r.status_code, r.text)
    r.raise_for_status()
    return r.json()
