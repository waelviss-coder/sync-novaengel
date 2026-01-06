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
    try:
        r = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            token = data.get("Token") or data.get("token")
            if token:
                return token
        return None
    except:
        return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE DIRECTEMENT la commande à NovaEngel"""
    logger.info("=== ENVOI COMMANDE NOVAENGEL ===")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Échec: pas de token")
            return False
        
        # 2. FIXEZ ICI VOS IDs PRODUIT - C'EST LA CLÉ !
        # Vous DEVEZ mettre les vrais IDs NovaEngel pour chaque SKU
        # Exemple: SKU "8436097094189" → ID NovaEngel "12345"
        SKU_TO_ID = {
            # ==== À VOUS DE REMPLIR ====
            # Format: "VOTRE_SKU": ID_NOVAENGEL,
            "8436097094189": 87061,  # REMPLACEZ 87061 par le VRAI ID
            "8436097094190": 2977,   # REMPLACEZ 2977 par le VRAI ID
            # ===========================
        }
        
        # 3. Préparer les lignes de commande
        lines = []
        for item in order.get("line_items", []):
            sku = str(item.get("sku", "")).strip()
            qty = item.get("quantity", 1)
            
            if not sku:
                continue
                
            # Trouver l'ID correspondant
            product_id = SKU_TO_ID.get(sku)
            
            if product_id:
                lines.append({
                    "productId": product_id,  # ← C'EST LE CHAMP IMPORTANT
                    "units": qty
                })
                logger.info(f"✅ SKU {sku} → ID {product_id} (qty: {qty})")
            else:
                # Si SKU non trouvé, ESSAYEZ avec un ID existant pour tester
                logger.warning(f"⚠ SKU non mappé: {sku} - ESSAI avec ID 87061")
                lines.append({
                    "productId": 87061,  # ID de test
                    "units": qty
                })
        
        if not lines:
            logger.error("❌ Aucun produit dans la commande")
            return False
        
        # 4. Adresse
        shipping = order.get("shipping_address", {})
        
        # 5. Numéro de commande (DOIT être numérique)
        order_number = order.get("name", "").replace("#", "")
        if not order_number.isdigit():
            # Générer un numéro numérique
            order_number = str(int(time.time()))[-9:]
            logger.info(f"📝 Numéro généré: {order_number}")
        
        # 6. PAYLOAD FINAL - FORMAT EXACT NovaEngel
        payload = [{
            "orderNumber": order_number[:15],  # Max 15 caractères
            "valoration": 0.0,
            "carrierNotes": "Commande Shopify",
            "lines": lines,  # ← Lignes produits
            "name": shipping.get("first_name", "Client"),
            "secondName": shipping.get("last_name", ""),
            "telephone": shipping.get("phone", "000000000"),
            "mobile": shipping.get("phone", "000000000"),
            "street": shipping.get("address1", ""),
            "city": shipping.get("city", ""),
            "county": shipping.get("province", ""),
            "postalCode": shipping.get("zip", "00000"),
            "country": shipping.get("country_code") or shipping.get("country", "FR")
        }]
        
        logger.info(f"📦 Payload prêt: {json.dumps(payload, indent=2)}")
        
        # 7. ENVOYER À NOVAENGEL
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        logger.info(f"🚀 Envoi à: {url}")
        
        response = requests.post(
            url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # 8. ANALYSER LA RÉPONSE
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        logger.info(f"📥 Contenu: {response.text}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"✅ SUCCÈS! Réponse: {json.dumps(result, indent=2)}")
                return True
            except:
                logger.info(f"✅ SUCCÈS (texte): {response.text}")
                return True
        else:
            logger.error(f"❌ ERREUR NovaEngel: {response.status_code}")
            logger.error(f"❌ Détails: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Exception: {str(e)}")
        return False