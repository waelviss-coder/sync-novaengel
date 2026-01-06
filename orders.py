import requests
import os
import time
import logging

# =========================== CONFIG ===========================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# =========================== LOGGER ===========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# =========================== TOKEN NOVA ENGEL ===========================
def get_novaengel_token():
    logger.info("🔑 Tentative d'obtenir le token NovaEngel...")
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
        logger.info(f"✅ Token reçu: {token[:6]}...")
        return token
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Impossible d'obtenir le token NovaEngel: {e}")
        raise

# =========================== STOCK ===========================
def get_novaengel_stock():
    token = get_novaengel_token()
    r = requests.get(f"https://drop.novaengel.com/api/stock/update/{token}", timeout=60)
    r.raise_for_status()
    return r.json()

# =========================== ENVOI DE COMMANDE ===========================
def send_order_to_novaengel(order):
    logger.info(f"📦 Nouvelle commande reçue: {order.get('name')}")
    try:
        token = get_novaengel_token()
        items = []
        for item in order.get("line_items", []):
            if item.get("sku"):
                items.append({
                    "Reference": item["sku"],
                    "Quantity": item["quantity"],
                    "Price": item["price"]
                })
        if not items:
            logger.warning("⚠ Aucun item valide trouvé dans la commande")

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
        logger.info(f"📤 Payload à envoyer à NovaEngel: {payload}")

        for attempt in range(3):
            try:
                r = requests.post(
                    f"https://drop.novaengel.com/api/order/create/{token}",
                    json=payload,
                    timeout=90
                )
                r.raise_for_status()
                logger.info(f"✅ Commande {payload['OrderNumber']} envoyée à NovaEngel")
                logger.info(f"💬 Réponse NovaEngel: {r.text}")
                break
            except requests.exceptions.ReadTimeout:
                logger.warning(f"⚠ Timeout, tentative {attempt+1}/3 dans 5s")
                time.sleep(5)
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Erreur lors de l'envoi à NovaEngel: {e}")
                break
    except Exception as e:
        logger.exception(f"❌ Échec envoi commande: {e}")
