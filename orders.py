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
        logger.error("❌ Pas de token")
        return None
    except Exception as e:
        logger.error(f"❌ Erreur token: {e}")
        return None

# =========================== RECHERCHE SIMPLE ===========================
def find_product_id_in_novaengel(sku, token):
    """Cherche un produit par SKU dans NovaEngel"""
    try:
        # Nettoyer le SKU
        sku_clean = str(sku).strip().replace("'", "")
        
        logger.info(f"🔍 Recherche SKU: '{sku_clean}'")
        
        # Chercher dans les 50 premiers produits seulement
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
        response = requests.get(url, timeout=20)
        
        if response.status_code != 200:
            return None
        
        products = response.json()
        
        for product in products:
            product_id = product.get("Id")
            if not product_id:
                continue
            
            # Vérifier différents champs
            description = product.get("Description", "")
            sku_field = product.get("SKU", "")
            full_code = product.get("FullCode", "")
            
            # Si le SKU correspond à un champ
            if (sku_clean == str(sku_field) or 
                sku_clean == str(full_code) or
                sku_clean in description):
                
                logger.info(f"✅ Produit trouvé: ID {product_id}")
                logger.info(f"   Description: {description[:50]}")
                return product_id
        
        logger.warning(f"⚠️ SKU non trouvé: '{sku_clean}'")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """Envoie la commande à NovaEngel"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            return False
        
        # 2. Traiter les produits
        order_number = order.get('name', 'N/A')
        items = order.get("line_items", [])
        
        logger.info(f"📦 Commande #{order_number}")
        
        lines = []
        for item in items:
            sku = str(item.get("sku", "")).strip()
            quantity = int(item.get("quantity", 1))
            
            if not sku:
                continue
            
            logger.info(f"   Produit: SKU '{sku}', Qty: {quantity}")
            
            # Chercher l'ID dans NovaEngel
            product_id = find_product_id_in_novaengel(sku, token)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"   ✅ ID trouvé: {product_id}")
            else:
                # BYPHASSE spécial - mapping direct connu
                if "8436097094189" in sku:
                    logger.info("🎯 BYPHASSE → ID 2731")
                    lines.append({
                        "productId": 2731,
                        "units": quantity
                    })
                else:
                    logger.error(f"❌ Produit non trouvé: {sku}")
                    return False
        
        if not lines:
            logger.error("❌ Aucun produit")
            return False
        
        # 3. Adresse
        shipping = order.get("shipping_address", {})
        
        # 4. Payload
        order_num = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-8:]
        
        payload = [{
            "orderNumber": order_num[:15],
            "valoration": 0.0,
            "carrierNotes": f"Shopify #{order.get('name', order_num)}",
            "lines": lines,
            "name": shipping.get("first_name", "Client")[:50],
            "secondName": shipping.get("last_name", "")[:50],
            "telephone": "600000000",
            "mobile": "600000000",
            "street": shipping.get("address1", "Adresse")[:100],
            "city": shipping.get("city", "Ville")[:50],
            "postalCode": shipping.get("zip", "00000")[:10],
            "country": (shipping.get("country_code") or "ES")[:2]
        }]
        
        logger.info(f"📦 Payload: {len(lines)} produit(s)")
        
        # 5. Envoi
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        # 6. Réponse
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                if isinstance(result, list) and result:
                    order_result = result[0]
                    if "Errors" in order_result and order_result["Errors"]:
                        for error in order_result["Errors"]:
                            logger.error(f"❌ Erreur: {error}")
                        return False
                    else:
                        booking_code = order_result.get('BookingCode')
                        if booking_code:
                            logger.info(f"🎉 BookingCode: {booking_code}")
                        return True
            except:
                pass
            return True
        else:
            logger.error(f"❌ Erreur {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Erreur: {e}")
        return False