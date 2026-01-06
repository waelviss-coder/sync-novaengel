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

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient le token NovaEngel"""
    try:
        response = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("Token") or data.get("token")
            if token:
                logger.info("🔑 Token obtenu")
                return token
        return None
    except Exception as e:
        logger.error(f"❌ Erreur token: {e}")
        return None

# =========================== RECHERCHE RÉELLE ===========================
def find_real_product_id(ean, token):
    """Trouve le VRAI ID dans NovaEngel pour un EAN"""
    # Nettoyer l'EAN
    ean_clean = str(ean).strip().replace("'", "")
    
    logger.info(f"🔍 Recherche RÉELLE EAN: {ean_clean}")
    
    try:
        # Chercher dans NovaEngel
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/100/en"
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ API error: {response.status_code}")
            return None
        
        products = response.json()
        logger.info(f"📊 {len(products)} produits analysés")
        
        # DEBUG: Afficher la structure
        if products:
            logger.info(f"🔍 Champs disponibles: {list(products[0].keys())}")
        
        # Chercher l'EAN
        found_products = []
        for product in products:
            product_id = product.get("Id")
            description = product.get("Description", "")
            
            # 1. Chercher dans EANS
            eans = product.get("EANS", [])
            for e in eans:
                if str(e).strip() == ean_clean:
                    logger.info(f"✅ EAN trouvé dans 'EANS'! ID: {product_id}")
                    logger.info(f"   Description: {description[:50]}")
                    logger.info(f"   EANS: {eans}")
                    return product_id
            
            # 2. Chercher dans d'autres champs
            sku = product.get("SKU", "")
            full_code = product.get("FullCode", "")
            barcode = product.get("Barcode", "")
            
            if ean_clean == str(sku):
                logger.info(f"✅ EAN trouvé dans 'SKU'! ID: {product_id}")
                return product_id
            
            if ean_clean == str(full_code):
                logger.info(f"✅ EAN trouvé dans 'FullCode'! ID: {product_id}")
                return product_id
            
            if ean_clean == str(barcode):
                logger.info(f"✅ EAN trouvé dans 'Barcode'! ID: {product_id}")
                return product_id
            
            # 3. Chercher dans description (BYPHASSE)
            if "BYPHASSE" in description.upper():
                logger.info(f"🔍 BYPHASSE trouvé: ID {product_id}")
                logger.info(f"   EANS: {eans}")
                logger.info(f"   SKU: {sku}")
                logger.info(f"   FullCode: {full_code}")
                
                if ean_clean in str(eans) or ean_clean in str(sku) or ean_clean in str(full_code):
                    logger.info(f"✅ BYPHASSE avec EAN correspondant! ID: {product_id}")
                    return product_id
        
        logger.error(f"❌ EAN {ean_clean} NON TROUVÉ dans NovaEngel")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """Envoie la commande à NovaEngel - Version FINALE"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Pas de token")
            return False
        
        # 2. Traiter produits
        items = order.get("line_items", [])
        lines = []
        
        for item in items:
            ean = str(item.get("sku", "")).strip()
            quantity = int(item.get("quantity", 1))
            
            if not ean:
                continue
            
            logger.info(f"📦 Traitement EAN: '{ean}', Qty: {quantity}")
            
            # Trouver le VRAI ID
            product_id = find_real_product_id(ean, token)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"   ✅ ID NovaEngel: {product_id}")
            else:
                logger.error(f"❌ EAN non trouvé dans NovaEngel: {ean}")
                return False
        
        if not lines:
            logger.error("❌ Aucun produit valide")
            return False
        
        # 3. Préparer payload
        shipping = order.get("shipping_address", {})
        order_num = order.get("name", "ORDER").replace("#", "").replace("TEST", "")
        
        # Téléphone
        phone = shipping.get("phone", "")
        if phone:
            phone_digits = ''.join(filter(str.isdigit, phone))
            phone = phone_digits if phone_digits else "600000000"
        else:
            phone = "600000000"
        
        payload = [{
            "orderNumber": order_num[:15],
            "valoration": 0.0,
            "carrierNotes": f"Shopify #{order.get('name', order_num)}",
            "lines": lines,
            "name": shipping.get("first_name", "Client")[:50],
            "secondName": shipping.get("last_name", "")[:50],
            "telephone": phone[:15],
            "mobile": phone[:15],
            "street": shipping.get("address1", "Adresse")[:100],
            "city": shipping.get("city", "Ville")[:50],
            "postalCode": shipping.get("zip", "00000")[:10],
            "country": (shipping.get("country_code") or "ES")[:2]
        }]
        
        logger.info(f"📦 Payload prêt: {len(lines)} produit(s)")
        
        # 4. Envoyer
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"📊 Réponse complète: {result}")
                
                if isinstance(result, list) and result:
                    order_result = result[0]
                    if "Errors" in order_result and order_result["Errors"]:
                        for error in order_result["Errors"]:
                            logger.error(f"❌ Erreur NovaEngel: {error}")
                        return False
                    else:
                        booking_code = order_result.get('BookingCode')
                        message = order_result.get('Message')
                        if booking_code:
                            logger.info(f"🎉 SUCCÈS! BookingCode: {booking_code}")
                        elif message:
                            logger.info(f"📝 Message: {message}")
                        else:
                            logger.info("✅ Commande acceptée")
                        return True
            except Exception as e:
                logger.error(f"❌ Erreur parsing JSON: {e}")
            
            logger.info("✅ Commande probablement acceptée")
            return True
        else:
            logger.error(f"❌ Erreur {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Erreur inattendue: {e}")
        return False