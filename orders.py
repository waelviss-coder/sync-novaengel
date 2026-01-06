import requests
import os
import time
import logging

# =========================
# CONFIG & CREDENTIALS
# =========================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

# =========================
# TOKEN NOVA ENGEL
# =========================
def get_novaengel_token():
    """
    Obtenir un token d'authentification NovaEngel.
    Timeout augmenté pour éviter les erreurs de timeout.
    """
    try:
        r = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            timeout=90
        )
        r.raise_for_status()
        token = r.json().get("Token") or r.json().get("token")
        if not token:
            raise Exception("Token NovaEngel manquant")
        logging.info("✅ Token NovaEngel obtenu")
        return token
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Erreur lors de la récupération du token : {e}")
        raise

# =========================
# ENVOI DE COMMANDE
# =========================
def send_order_to_novaengel(order):
    """
    Envoie la commande Shopify vers NovaEngel avec retry automatique 3 fois.
    """
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
                timeout=90
            )
            r.raise_for_status()
            logging.info(f"✅ Commande {payload['OrderNumber']} envoyée à NovaEngel")
            return r.json()
        except requests.exceptions.ReadTimeout:
            logging.warning(f"⚠ Timeout, nouvelle tentative {attempt+1}/3 dans 5s")
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Erreur lors de l'envoi de la commande : {e}")
            raise
    raise Exception(f"La commande {payload['OrderNumber']} n'a pas pu être envoyée après 3 tentatives")
