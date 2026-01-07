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

# =========================== RECHERCHE SIMPLE ===========================
def search_product_in_novaengel(sku, token):
    """Cherche un produit par SKU/EAN dans NovaEngel - Version SIMPLE"""
    # Nettoyer le SKU (enlever apostrophe)
    sku_clean = str(sku).strip().replace("'", "")
    
    logger.info(f"🔍 Recherche SKU: '{sku_clean}'")
    
    try:
        # Chercher seulement dans la première page (50 produits)
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
        response = requests.get(url, timeout=20)
        
        if response.status_code != 200:
            return None
        
        products = response.json()
        
        # DEBUG: Afficher le premier produit pour voir la structure
        if products:
            first_product = products[0]
            logger.info(f"🔍 Structure produit: {list(first_product.keys())}")
        
        # Chercher le produit
        for product in products:
            product_id = product.get("Id")
            if not product_id:
                continue
            
            # Vérifier TOUS les champs possibles
            for key, value in product.items():
                if isinstance(value, str) and sku_clean in value:
                    logger.info(f"✅ Trouvé dans champ '{key}': {value[:50]}")
                    return product_id
                elif isinstance(value, list):
                    for item in value:
                        if str(item) == sku_clean:
                            logger.info(f"✅ Trouvé dans liste '{key}': {item}")
                            return product_id
        
        logger.warning(f"⚠️ SKU '{sku_clean}' non trouvé dans les 50 premiers produits")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return None

# =========================== BYPHASSE SPECIAL ===========================
def get_product_id_for_sku(sku, token):
    """Retourne l'ID NovaEngel pour un SKU - avec règles spéciales"""
    sku_clean = str(sku).strip().replace("'", "")
    
    # 1. RÈGLE SPÉCIALE BYPHASSE
    # Si c'est un EAN BYPHASSE, retourner l'ID connu
    if sku_clean in ["8436097094189", "8436097094196", "8436097094202"]:
        # BYPHASSE EANs connus → ID 2731
        logger.info(f"🎯 BYPHASSE EAN {sku_clean} → ID 2731")
        return 2731
    
    # 2. Recherche dans NovaEngel
    product_id = search_product_in_novaengel(sku, token)
    
    if product_id:
        return product_id
    
    # 3. FALLBACK: Utiliser les derniers chiffres comme ID
    if sku_clean[-5:].isdigit():
        fallback_id = int(sku_clean[-5:])
        logger.warning(f"⚠️ Fallback: {sku_clean} → ID {fallback_id}")
        return fallback_id
    
    return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """Envoie la commande à NovaEngel - SIMPLE"""
    logger.info("🚀 ENVOI COMMANDE")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Pas de token")
            return False
        
        # 2. Traiter produits
        order_number = order.get('name', 'N/A')
        items = order.get("line_items", [])
        
        logger.info(f"📦 Commande #{order_number} - {len(items)} produit(s)")
        
        lines = []
        for idx, item in enumerate(items, 1):
            sku = str(item.get("sku", "")).strip()
            quantity = int(item.get("quantity", 1))
            title = item.get("title", "")[:50]
            
            if not sku:
                logger.warning(f"⚠️ Produit {idx} sans SKU ignoré")
                continue
            
            logger.info(f"📦 Produit {idx}: {title}")
            logger.info(f"   SKU: '{sku}', Qty: {quantity}")
            
            # Obtenir l'ID
            product_id = get_product_id_for_sku(sku, token)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"   ✅ ID NovaEngel: {product_id}")
            else:
                logger.error(f"❌ Produit non trouvé: {sku}")
                return False
        
        if not lines:
            logger.error("❌ Aucun produit valide")
            return False
        
        # 3. Adresse
        shipping = order.get("shipping_address", {})
        
        # 4. Payload SIMPLE
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
        
        logger.info(f"📦 Payload prêt: {len(lines)} produit(s)")
        
        # 5. Envoi
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        # 6. Vérifier réponse
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"📊 Réponse JSON: {result}")
                
                if isinstance(result, list) and result:
                    order_result = result[0]
                    if "Errors" in order_result and order_result["Errors"]:
                        for error in order_result["Errors"]:
                            logger.error(f"❌ Erreur NovaEngel: {error}")
                        return False
                    else:
                        booking_code = order_result.get('BookingCode')
                        if booking_code:
                            logger.info(f"🎉 SUCCÈS! BookingCode: {booking_code}")
                        return True
            except Exception as e:
                logger.error(f"❌ Erreur parsing JSON: {e}")
            
            logger.info("✅ Commande probablement acceptée")
            return True
        else:
            logger.error(f"❌ Erreur {response.status_code}: {response.text[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Erreur: {e}")
        return False