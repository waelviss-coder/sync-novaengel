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

# =========================== RECHERCHE PRODUIT PAR EAN ===========================
def find_product_id_by_ean(ean, token):
    """Recherche l'ID produit à partir de l'EAN"""
    try:
        # Télécharger la liste des produits
        r = requests.get(
            f"https://drop.novaengel.com/api/products/availables/{token}/en",
            timeout=60
        )
        r.raise_for_status()
        products = r.json()
        
        # Rechercher par EAN
        for product in products:
            if "EANS" in product and ean in product["EANS"]:
                return product["Id"]
        return None
    except Exception as e:
        logger.error(f"❌ Erreur recherche produit EAN {ean}: {e}")
        return None

# =========================== ENVOI DE COMMANDE CORRIGÉ ===========================
def send_order_to_novaengel(order):
    logger.info(f"📦 Nouvelle commande reçue: {order.get('name')}")
    
    try:
        # 1. Obtenir le token
        token = get_novaengel_token()
        
        # 2. Préparer les lignes de commande
        order_lines = []
        for item in order.get("line_items", []):
            if item.get("sku"):
                # Rechercher l'ID produit à partir du SKU (EAN)
                product_id = find_product_id_by_ean(item["sku"], token)
                if product_id:
                    order_lines.append({
                        "productId": product_id,  # Note: minuscule comme dans OrderInLineModel
                        "units": item["quantity"]  # Note: minuscule
                    })
                    logger.info(f"✅ Produit trouvé: EAN {item['sku']} → ID {product_id}")
                else:
                    logger.warning(f"⚠ Produit non trouvé pour EAN: {item['sku']}")
        
        if not order_lines:
            logger.error("❌ Aucun produit valide trouvé dans la commande")
            return
        
        # 3. Récupérer l'adresse de livraison
        shipping = order.get("shipping_address", {})
        
        # 4. Construire le payload selon OrderInModel
        payload = [{
            "orderNumber": order.get("name", "").replace("#", ""),  # Numérique uniquement selon manuel
            "valoration": 0.0,  # Optionnel
            "carrierNotes": "",  # Optionnel
            "lines": order_lines,
            "name": shipping.get("first_name", ""),
            "secondName": shipping.get("last_name", ""),
            "telephone": shipping.get("phone", ""),
            "mobile": shipping.get("phone", ""),  # Même que téléphone si pas de mobile
            "street": shipping.get("address1", ""),
            "city": shipping.get("city", ""),
            "county": shipping.get("province", ""),
            "postalCode": shipping.get("zip", ""),
            "country": shipping.get("country_code", shipping.get("country", ""))
        }]
        
        logger.info(f"📤 Payload à envoyer à NovaEngel: {payload}")
        
        # 5. Envoyer la commande
        for attempt in range(3):
            try:
                # CORRECTION: Utiliser le bon endpoint
                r = requests.post(
                    f"https://drop.novaengel.com/api/orders/sendv2/{token}",
                    json=payload,  # Note: liste d'ordres
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    timeout=90
                )
                
                logger.info(f"📥 Réponse NovaEngel (status {r.status_code}): {r.text}")
                
                if r.status_code == 200:
                    response_data = r.json()
                    if response_data and isinstance(response_data, list):
                        for order_response in response_data:
                            if "Errors" in order_response and order_response["Errors"]:
                                logger.error(f"❌ Erreurs NovaEngel: {order_response['Errors']}")
                            else:
                                logger.info(f"✅ Commande envoyée avec succès! BookingCode: {order_response.get('BookingCode', 'N/A')}")
                    return
                else:
                    r.raise_for_status()
                    
            except requests.exceptions.ReadTimeout:
                logger.warning(f"⚠ Timeout, tentative {attempt+1}/3 dans 5s")
                time.sleep(5)
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Erreur lors de l'envoi à NovaEngel (tentative {attempt+1}): {e}")
                if attempt == 2:  # Dernière tentative
                    raise
                time.sleep(5)
                
    except Exception as e:
        logger.exception(f"❌ Échec envoi commande: {e}")