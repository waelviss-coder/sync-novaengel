import requests
import os
import time
import logging
import json

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
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        logger.info(f"📥 Login status: {r.status_code}")
        
        if r.status_code != 200:
            logger.error(f"❌ Erreur login: {r.text}")
            return None
            
        data = r.json()
        token = data.get("Token") or data.get("token")
        
        if not token:
            logger.error("❌ Token non trouvé")
            return None
            
        logger.info(f"✅ Token reçu: {token[:8]}...")
        return token
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur réseau login: {e}")
        return None
    except Exception as e:
        logger.exception(f"❌ Exception login: {e}")
        return None

# =========================== STOCK ===========================
def get_novaengel_stock():
    logger.info("🔍 Récupération stock NovaEngel...")
    token = get_novaengel_token()
    if not token:
        logger.error("❌ Pas de token pour stock")
        return []
    
    try:
        r = requests.get(
            f"https://drop.novaengel.com/api/stock/update/{token}",
            headers={"Accept": "application/json"},
            timeout=60
        )
        
        if r.status_code == 200:
            return r.json()
        else:
            logger.error(f"❌ Erreur stock: {r.status_code} - {r.text}")
            return []
    except Exception as e:
        logger.exception(f"❌ Exception stock: {e}")
        return []

# =========================== RECHERCHE PRODUIT PAR EAN ===========================
def find_product_id_by_ean(ean, token):
    """Recherche l'ID produit à partir de l'EAN"""
    if not ean or not token:
        return None
        
    try:
        logger.info(f"🔍 Recherche ID pour EAN: {ean}")
        
        # Télécharger la liste des produits
        r = requests.get(
            f"https://drop.novaengel.com/api/products/availables/{token}/en",
            headers={"Accept": "application/json"},
            timeout=60
        )
        
        if r.status_code != 200:
            logger.error(f"❌ Erreur produits: {r.status_code}")
            return None
            
        products = r.json()
        
        # Rechercher par EAN
        for product in products:
            if "EANS" in product and ean in product["EANS"]:
                logger.info(f"✅ Produit trouvé: EAN {ean} → ID {product['Id']}")
                return product["Id"]
        
        logger.warning(f"⚠ Produit non trouvé pour EAN: {ean}")
        return None
        
    except Exception as e:
        logger.exception(f"❌ Erreur recherche produit EAN {ean}: {e}")
        return None

# =========================== ENVOI DE COMMANDE CORRIGÉ ===========================
def send_order_to_novaengel(order):
    logger.info("=== DÉBUT ENVOI COMMANDE NOVAENGEL ===")
    logger.info(f"📦 Commande: {order.get('name', 'N/A')}")
    
    try:
        # 1. Obtenir le token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Impossible d'obtenir le token")
            return
        
        # 2. Préparer les lignes de commande
        order_lines = []
        line_items = order.get("line_items", [])
        logger.info(f"📦 Nombre d'items: {len(line_items)}")
        
        for item in line_items:
            sku = item.get("sku", "").strip()
            if not sku:
                logger.warning("⚠ Item sans SKU ignoré")
                continue
                
            # Rechercher l'ID produit à partir du SKU (EAN)
            product_id = find_product_id_by_ean(sku, token)
            if product_id:
                order_lines.append({
                    "productId": product_id,
                    "units": item.get("quantity", 1)
                })
                logger.info(f"✅ Item ajouté: {sku} → ID {product_id}, Qty: {item.get('quantity', 1)}")
            else:
                logger.warning(f"⚠ Produit non trouvé pour EAN: {sku}")
        
        if not order_lines:
            logger.error("❌ Aucun produit valide trouvé dans la commande")
            return
        
        # 3. Récupérer l'adresse de livraison
        shipping = order.get("shipping_address", {})
        
        # 4. Construire le payload selon OrderInModel
        order_number = order.get("name", "").replace("#", "").replace("TEST", "")
        # S'assurer que c'est numérique (requis par NovaEngel)
        if not order_number.isdigit():
            order_number = str(int(time.time()))[-10:]  # Générer un numéro numérique
            logger.info(f"⚠ Numéro de commande modifié: {order.get('name', '')} → {order_number}")
        
        payload = [{
            "orderNumber": order_number,
            "valoration": 0.0,
            "carrierNotes": "Commande depuis Shopify",
            "lines": order_lines,
            "name": shipping.get("first_name", ""),
            "secondName": shipping.get("last_name", ""),
            "telephone": shipping.get("phone", "") or "0000000000",
            "mobile": shipping.get("phone", "") or "0000000000",
            "street": shipping.get("address1", ""),
            "city": shipping.get("city", ""),
            "county": shipping.get("province", ""),
            "postalCode": shipping.get("zip", ""),
            "country": shipping.get("country_code") or shipping.get("country", "ES")
        }]
        
        logger.info(f"📤 Payload NovaEngel: {json.dumps(payload, indent=2)}")
        
        # 5. Envoyer la commande avec retry
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        for attempt in range(3):
            logger.info(f"📤 Tentative {attempt+1}/3: {url}")
            
            try:
                r = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=60
                )
                
                logger.info(f"📥 Réponse NovaEngel (status {r.status_code}): {r.text[:500]}")
                
                if r.status_code == 200:
                    try:
                        response_data = r.json()
                        logger.info(f"📥 Réponse JSON: {response_data}")
                        
                        if isinstance(response_data, list):
                            for order_response in response_data:
                                if "Errors" in order_response and order_response["Errors"]:
                                    logger.error(f"❌ Erreurs NovaEngel: {order_response['Errors']}")
                                else:
                                    logger.info(f"✅ Commande envoyée avec succès! BookingCode: {order_response.get('BookingCode', 'N/A')}")
                                    logger.info(f"✅ Message: {order_response.get('Message', 'N/A')}")
                        else:
                            logger.info(f"✅ Réponse: {response_data}")
                    except:
                        logger.info(f"✅ Réponse texte: {r.text}")
                    
                    logger.info("=== COMMANDE ENVOYÉE AVEC SUCCÈS ===")
                    return
                else:
                    logger.error(f"❌ Erreur HTTP {r.status_code}: {r.text}")
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    
            except requests.exceptions.Timeout:
                logger.warning(f"⚠ Timeout, tentative {attempt+1}/3")
                if attempt < 2:
                    time.sleep(5)
                    continue
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Erreur réseau (tentative {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(2)
                    continue
                    
            except Exception as e:
                logger.exception(f"❌ Erreur inattendue: {e}")
                break
        
        logger.error("❌ Échec après 3 tentatives")
        
    except Exception as e:
        logger.exception(f"❌ Échec complet envoi commande: {e}")