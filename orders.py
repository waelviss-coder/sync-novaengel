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

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient le token NovaEngel avec timeout court"""
    try:
        logger.info("🔑 Connexion à NovaEngel...")
        response = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=10  # Timeout court
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("Token") or data.get("token")
            if token:
                logger.info("✅ Token obtenu")
                return token
            else:
                logger.error("❌ Token non trouvé dans la réponse")
        else:
            logger.error(f"❌ Erreur login: {response.status_code}")
        
        return None
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout connexion NovaEngel")
        return None
    except Exception as e:
        logger.error(f"❌ Exception login: {e}")
        return None

# =========================== MAPPING DIRECT ===========================
# Mapping EAN → ID NovaEngel (config statique)
PRODUCT_MAPPING = {
    # BYPHASSE - Basé sur vos données
    "'8436097094189": 94189,  # Format Shopify
    "8436097094189": 94189,   # Format nettoyé
    "094189": 94189,          # Code court
    "94189": 94189,           # FullCode
    
    # Autres produits
    "'0729238187061": 87061,
    "0729238187061": 87061,
    
    # Ajoutez d'autres produits ici
}

def get_product_id(sku):
    """Trouve l'ID produit - MAPPING DIRECT (pas de recherche API)"""
    # Nettoyer le SKU
    sku_clean = str(sku).strip()
    
    # 1. Chercher dans le mapping exact
    if sku_clean in PRODUCT_MAPPING:
        product_id = PRODUCT_MAPPING[sku_clean]
        logger.info(f"✅ Mapping direct: '{sku_clean}' → {product_id}")
        return product_id
    
    # 2. Chercher version sans apostrophe
    sku_no_apostrophe = sku_clean.replace("'", "")
    if sku_no_apostrophe in PRODUCT_MAPPING:
        product_id = PRODUCT_MAPPING[sku_no_apostrophe]
        logger.info(f"✅ Mapping nettoyé: '{sku_no_apostrophe}' → {product_id}")
        return product_id
    
    # 3. BYPHASSE spécial (fallback)
    if "8436097094189" in sku_no_apostrophe:
        logger.info(f"🎯 BYPHASSE détecté → 94189")
        return 94189
    
    logger.error(f"❌ SKU non mappé: '{sku_clean}'")
    return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """Envoie la commande à NovaEngel - OPTIMISÉ pour Render"""
    logger.info("🚀 Début envoi commande")
    start_time = time.time()
    
    try:
        # 1. Token (avec retry)
        token = None
        for attempt in range(2):  # 2 tentatives max
            token = get_novaengel_token()
            if token:
                break
            if attempt < 1:
                logger.info("🔄 Nouvelle tentative token...")
                time.sleep(1)
        
        if not token:
            logger.error("❌ Impossible d'obtenir le token après 2 tentatives")
            return False
        
        # 2. Valider produits
        order_number = order.get('name', 'N/A')
        items = order.get("line_items", [])
        
        logger.info(f"📦 Commande #{order_number} - {len(items)} produit(s)")
        
        lines = []
        for idx, item in enumerate(items, 1):
            sku = str(item.get("sku", "")).strip()
            quantity = int(item.get("quantity", 1))
            title = item.get("title", "")[:30]
            
            if not sku:
                logger.warning(f"⚠️ Produit {idx} sans SKU ignoré")
                continue
            
            logger.info(f"   Produit {idx}: {title}")
            
            # Trouver l'ID (mapping direct)
            product_id = get_product_id(sku)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"     ✅ ID: {product_id}, Qty: {quantity}")
            else:
                logger.error(f"     ❌ Produit non mappé: {sku}")
                return False
        
        if not lines:
            logger.error("❌ Aucun produit valide")
            return False
        
        # 3. Préparer payload
        shipping = order.get("shipping_address", {})
        
        # Nettoyer téléphone
        phone = shipping.get("phone", "")
        if phone:
            phone_digits = ''.join(filter(str.isdigit, phone))
            phone = phone_digits if len(phone_digits) >= 9 else "600000000"
        else:
            phone = "600000000"
        
        # Numéro de commande
        order_num = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-8:]
        
        # Payload optimisé
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
            "country": (shipping.get("country_code") or shipping.get("country") or "ES")[:2]
        }]
        
        logger.info(f"📦 Payload prêt: {len(lines)} produit(s)")
        
        # 4. Envoi à NovaEngel (timeout court)
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        
        response = requests.post(
            url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=15  # Timeout court pour Render
        )
        
        # 5. Analyser réponse
        logger.info(f"📥 Réponse NovaEngel: HTTP {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                
                success = True
                error_messages = []
                
                if isinstance(result, list):
                    for order_result in result:
                        if "Errors" in order_result and order_result["Errors"]:
                            for error in order_result["Errors"]:
                                error_messages.append(error)
                                logger.error(f"❌ Erreur NovaEngel: {error}")
                                success = False
                        else:
                            booking_code = order_result.get('BookingCode')
                            message = order_result.get('Message')
                            if booking_code:
                                logger.info(f"🎉 Commande créée! BookingCode: {booking_code}")
                            elif message and message != "KO":
                                logger.info(f"📝 Message: {message}")
                
                if success:
                    elapsed = time.time() - start_time
                    logger.info(f"✨ SUCCÈS! Commande envoyée en {elapsed:.1f}s")
                    return True
                else:
                    logger.error(f"❌ Commande échouée: {', '.join(error_messages)}")
                    return False
                    
            except json.JSONDecodeError:
                logger.info("📝 Réponse texte (non-JSON)")
                # Même si ce n'est pas du JSON, un 200 est généralement bon
                elapsed = time.time() - start_time
                logger.info(f"✅ Commande probablement acceptée ({elapsed:.1f}s)")
                return True
                
        else:
            logger.error(f"❌ Erreur HTTP {response.status_code}: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de l'envoi à NovaEngel")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur réseau: {e}")
        return False
    except Exception as e:
        logger.error(f"💥 Exception inattendue: {e}")
        return False
    finally:
        elapsed = time.time() - start_time
        logger.info(f"⏱️ Temps total: {elapsed:.1f}s")