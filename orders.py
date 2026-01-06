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

# Cache simple pour éviter recherches répétées
_product_cache = {}
_cache_timestamp = None
CACHE_DURATION = 300  # 5 minutes

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
                logger.info("🔑 Token NovaEngel obtenu")
                return token
            else:
                logger.error("❌ Token non trouvé dans la réponse")
        else:
            logger.error(f"❌ Erreur login: {response.status_code}")
        
        return None
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors du login")
        return None
    except Exception as e:
        logger.error(f"❌ Exception login: {e}")
        return None

# =========================== RECHERCHE PRODUIT ===========================
def load_product_cache(token):
    """Charge les produits en cache"""
    global _product_cache, _cache_timestamp
    
    # Vérifier si le cache est encore valide
    if _cache_timestamp and (datetime.now() - _cache_timestamp).seconds < CACHE_DURATION:
        return _product_cache
    
    logger.info("📚 Chargement du cache produits...")
    
    try:
        cache = {}
        page = 0
        total_loaded = 0
        
        # Charger 200 produits maximum pour rapidité
        while total_loaded < 200:
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/50/en"
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur chargement page {page}")
                break
            
            products = response.json()
            if not products:
                break
            
            # Ajouter au cache
            for product in products:
                product_id = product.get("Id")
                eans = product.get("EANS", [])
                
                for ean in eans:
                    if ean and product_id:
                        # Nettoyer l'EAN
                        ean_clean = str(ean).strip()
                        cache[ean_clean] = product_id
            
            total_loaded += len(products)
            logger.info(f"📖 Page {page}: {len(products)} produits, cache: {len(cache)} EANs")
            
            if len(products) < 50:
                break
            
            page += 1
        
        _product_cache = cache
        _cache_timestamp = datetime.now()
        
        logger.info(f"✅ Cache chargé: {total_loaded} produits, {len(cache)} EANs")
        return cache
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

def find_product_id(ean, token):
    """Trouve l'ID produit pour un EAN"""
    global _product_cache
    
    # Nettoyer l'EAN
    ean_clean = str(ean).strip().replace("'", "").replace('"', '')
    
    # Recharger le cache si nécessaire
    if not _product_cache:
        load_product_cache(token)
    
    # Chercher dans le cache
    if ean_clean in _product_cache:
        product_id = _product_cache[ean_clean]
        logger.info(f"✅ Cache: {ean_clean} → ID {product_id}")
        return product_id
    
    # Si pas dans le cache, chercher directement
    logger.info(f"🔍 Recherche directe: {ean_clean}")
    
    try:
        # Recherche dans les premiers produits
        url = f"https://drop.novaengel.com/api/products/paging/{token}/0/20/en"
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
        
        if response.status_code != 200:
            return None
        
        products = response.json()
        
        for product in products:
            eans = product.get("EANS", [])
            if ean_clean in eans:
                product_id = product.get("Id")
                # Ajouter au cache
                _product_cache[ean_clean] = product_id
                logger.info(f"✅ Direct: {ean_clean} → ID {product_id}")
                return product_id
        
        logger.warning(f"⚠️ EAN non trouvé: {ean_clean}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche: {e}")
        return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel"""
    logger.info("🚀 DÉBUT ENVOI COMMANDE")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Impossible d'obtenir le token")
            return False
        
        # 2. Préparer les lignes de commande
        lines = []
        items = order.get("line_items", [])
        logger.info(f"📦 Commande: {order.get('name', 'N/A')}, Items: {len(items)}")
        
        for idx, item in enumerate(items, 1):
            ean = str(item.get("sku", "")).strip()
            quantity = item.get("quantity", 1)
            
            if not ean:
                logger.warning(f"⚠️ Item {idx} sans EAN ignoré")
                continue
            
            # Chercher l'ID produit
            product_id = find_product_id(ean, token)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"✅ Item {idx}: {ean} → ID {product_id} (qty: {quantity})")
            else:
                logger.error(f"❌ Item {idx}: EAN non trouvé - {ean}")
                return False  # Arrêter si un EAN n'est pas trouvé
        
        if not lines:
            logger.error("❌ Aucun produit valide trouvé")
            return False
        
        # 3. Préparer l'adresse
        shipping = order.get("shipping_address", {})
        
        # 4. Numéro de commande (doit être numérique)
        order_number = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_number.isdigit():
            order_number = str(int(time.time()))[-10:]
            logger.info(f"📝 Numéro généré: {order_number}")
        
        # 5. PAYLOAD FINAL
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
        
        logger.info(f"📦 Payload prêt - Commande #{order_number}")
        
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
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info("✅ SUCCÈS! Réponse NovaEngel:")
                
                success = True
                if isinstance(result, list):
                    for order_result in result:
                        if "Errors" in order_result and order_result["Errors"]:
                            for error in order_result["Errors"]:
                                logger.error(f"❌ Erreur NovaEngel: {error}")
                                success = False
                        else:
                            booking_code = order_result.get('BookingCode')
                            message = order_result.get('Message')
                            logger.info(f"🎉 BookingCode: {booking_code or 'N/A'}")
                            logger.info(f"💬 Message: {message or 'N/A'}")
                
                if success:
                    logger.info("✨ COMMANDE ENVOYÉE AVEC SUCCÈS!")
                else:
                    logger.error("❌ Commande avec erreurs")
                
                return success
                
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
        logger.info("📊 Récupération stock...")
        
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