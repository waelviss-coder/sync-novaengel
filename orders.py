import requests
import os
import time
import logging
import json
from datetime import datetime, timedelta

# =========================== CONFIG ===========================
NOVA_USER = os.environ.get("NOVA_USER")
NOVA_PASS = os.environ.get("NOVA_PASS")

# =========================== LOGGER ===========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# =========================== MAPPING MANUEL EAN → ID ===========================
# ⚠️ VOUS DEVEZ REMPLIR CE DICTIONNAIRE MANUELLEMENT
# Format: "VOTRE_EAN_DANS_SHOPIFY": ID_NOVAENGEL
EAN_TO_ID = {
    # ==== EXEMPLES - À ADAPTER ====
    "0729238187061": 87061,    # SHISEIDO - SYNCHRO SKIN
    "8436097094189": 94189,    # BYPHASSE - MOISTURIZING LIP BALM
    
    # Si vos SKUs Shopify sont les IDs NovaEngel directement:
    "87061": 87061,
    "94189": 94189,
    
    # ==== AJOUTEZ TOUS VOS EANs ICI ====
    # "EAN_EXEMPLE": ID_CORRESPONDANT,
}

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient le token NovaEngel"""
    try:
        response = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("Token") or data.get("token")
            if token:
                logger.info(f"🔑 Token obtenu")
                return token
        logger.error(f"❌ Erreur login: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"❌ Exception login: {e}")
        return None

# =========================== ENVOI COMMANDE SIMPLE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel - VERSION SIMPLE ET EFFICACE"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Obtenir le token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Impossible d'obtenir le token")
            return False
        
        # 2. Préparer les lignes de commande
        lines = []
        items = order.get("line_items", [])
        
        for item in items:
            sku = str(item.get("sku", "")).strip()
            quantity = item.get("quantity", 1)
            
            if not sku:
                logger.warning("⚠️ Item sans SKU ignoré")
                continue
            
            # CHERCHER L'ID DANS LE MAPPING MANUEL
            product_id = EAN_TO_ID.get(sku)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"✅ {sku} → ID {product_id} (qty: {quantity})")
            else:
                # Si SKU non trouvé, ESSAYER si c'est déjà un ID numérique
                if sku.isdigit():
                    product_id = int(sku)
                    lines.append({
                        "productId": product_id,
                        "units": quantity
                    })
                    logger.warning(f"⚠️ {sku} utilisé comme ID (numérique)")
                else:
                    logger.error(f"❌ SKU non mappé: {sku} - item ignoré")
        
        if not lines:
            logger.error("❌ Aucun produit valide dans la commande")
            return False
        
        # 3. Préparer l'adresse
        shipping = order.get("shipping_address", {})
        
        # 4. Numéro de commande (DOIT être numérique)
        order_number = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_number.isdigit():
            order_number = str(int(time.time()))[-10:]
            logger.info(f"📝 Numéro généré: {order_number}")
        
        # 5. PAYLOAD FINAL - Format exact NovaEngel
        payload = [{
            "orderNumber": order_number[:15],  # Max 15 caractères
            "valoration": 0.0,
            "carrierNotes": f"Commande Shopify #{order.get('name', order_number)}",
            "lines": lines,
            "name": shipping.get("first_name", "Client"),
            "secondName": shipping.get("last_name", ""),
            "telephone": shipping.get("phone", "0000000000"),
            "mobile": shipping.get("phone", "0000000000"),
            "street": shipping.get("address1", "Adresse"),
            "city": shipping.get("city", "Ville"),
            "county": shipping.get("province", ""),
            "postalCode": shipping.get("zip", "00000"),
            "country": shipping.get("country_code") or shipping.get("country", "FR")
        }]
        
        logger.info(f"📦 Payload prêt pour commande #{order_number}")
        logger.info(f"📦 Contenu: {len(lines)} produits")
        
        # 6. ENVOYER À NOVAENGEL
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        logger.info(f"🌐 Envoi à NovaEngel...")
        
        response = requests.post(
            url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # 7. ANALYSER LA RÉPONSE
        logger.info(f"📥 Réponse NovaEngel: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info("✅ SUCCÈS! Commande envoyée à NovaEngel")
                
                # Vérifier les erreurs détaillées
                if isinstance(result, list):
                    for order_result in result:
                        if "Errors" in order_result and order_result["Errors"]:
                            for error in order_result["Errors"]:
                                logger.error(f"❌ Erreur NovaEngel: {error}")
                            return False
                        else:
                            logger.info(f"🎉 BookingCode: {order_result.get('BookingCode', 'N/A')}")
                            logger.info(f"💬 Message: {order_result.get('Message', 'N/A')}")
                return True
                
            except json.JSONDecodeError:
                logger.info(f"✅ Réponse texte: {response.text[:200]}")
                return True
                
        else:
            logger.error(f"❌ ERREUR {response.status_code}")
            logger.error(f"❌ Détails: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de l'envoi")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur réseau: {e}")
        return False
    except Exception as e:
        logger.error(f"💥 Exception inattendue: {e}")
        return False

# =========================== STOCK ===========================
def get_novaengel_stock():
    """Récupère le stock NovaEngel"""
    token = get_novaengel_token()
    if not token:
        logger.error("❌ Pas de token pour stock")
        return []
    
    try:
        url = f"https://drop.novaengel.com/api/stock/update/{token}"
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            stock_data = response.json()
            logger.info(f"📊 Stock récupéré: {len(stock_data)} produits")
            return stock_data
        else:
            logger.error(f"❌ Erreur stock: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"❌ Exception stock: {e}")
        return []