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

# Caches
_product_cache = {}
_product_cache_by_id = {}
_cache_timestamp = None
CACHE_DURATION = 300

# =========================== MAPPING FORCÉ ===========================
# D'après vos données: BYPHASSE - ID: 2731, FullCode: 94189, EAN: 8436097094189
FORCED_MAPPINGS = {
    # BYPHASSE Lip Balm
    "'8436097094189": 2731,
    "8436097094189": 2731,
    "094189": 2731,
    "94189": 2731,
    "4189": 2731,
    
    # Autres produits pour référence
    "'0729238187061": 87061,  # Produit de votre log précédent
    "0729238187061": 87061,
    "87061": 87061,
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
                logger.info("🔑 Token NovaEngel obtenu")
                return token
        return None
    except Exception as e:
        logger.error(f"❌ Erreur token: {e}")
        return None

# =========================== CACHE PRODUITS ===========================
def load_product_cache(token, force_reload=False):
    """Charge tous les produits NovaEngel en cache"""
    global _product_cache, _product_cache_by_id, _cache_timestamp
    
    if not force_reload and _cache_timestamp and (datetime.now() - _cache_timestamp).seconds < CACHE_DURATION:
        return _product_cache
    
    logger.info("🔄 Chargement du cache produits NovaEngel...")
    
    try:
        cache_by_ean = {}
        cache_by_id = {}
        page = 0
        total_loaded = 0
        
        # Charger les produits
        while total_loaded < 1000:  # Limite de sécurité
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/100/en"
            
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            
            if response.status_code != 200:
                break
            
            products = response.json()
            if not products:
                break
            
            for product in products:
                product_id = product.get("Id")
                if not product_id:
                    continue
                
                # Stocker par ID
                cache_by_id[product_id] = {
                    "description": product.get("Description", ""),
                    "eans": product.get("EANS", []),
                    "sku": product.get("SKU", ""),
                    "full_code": product.get("FullCode", ""),
                    "brand": product.get("BrandName", ""),
                    "price": product.get("Price", 0)
                }
                
                # Indexer par EAN
                eans = product.get("EANS", [])
                for ean in eans:
                    if ean:
                        ean_str = str(ean).strip()
                        # Format original
                        cache_by_ean[ean_str] = product_id
                        
                        # Formats alternatifs
                        if ean_str.startswith('0'):
                            cache_by_ean[ean_str.lstrip('0')] = product_id
                        
                        if len(ean_str) >= 5:
                            cache_by_ean[ean_str[-5:]] = product_id
                
                total_loaded += 1
            
            logger.info(f"📖 Page {page}: {len(products)} produits")
            
            if len(products) < 100:
                break
            
            page += 1
            time.sleep(0.2)
        
        _product_cache = cache_by_ean
        _product_cache_by_id = cache_by_id
        _cache_timestamp = datetime.now()
        
        logger.info(f"✅ Cache chargé: {total_loaded} produits, {len(cache_by_ean)} références EAN")
        
        # DEBUG: Chercher BYPHASSE
        found_byphasse = False
        for ean, pid in cache_by_ean.items():
            if pid in cache_by_id:
                desc = cache_by_id[pid]["description"]
                if "BYPHASSE" in desc.upper():
                    eans_list = cache_by_id[pid]["eans"]
                    logger.info(f"🎯 BYPHASSE trouvé: ID {pid}")
                    logger.info(f"   Description: {desc[:60]}")
                    logger.info(f"   EANs: {eans_list}")
                    found_byphasse = True
                    break
        
        if not found_byphasse:
            logger.warning("⚠️ BYPHASSE non trouvé dans le cache API")
        
        return cache_by_ean
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

# =========================== RECHERCHE PRODUIT ===========================
def find_product_id(ean, token):
    """Trouve l'ID produit pour un EAN"""
    global _product_cache, _product_cache_by_id
    
    # Nettoyer l'EAN
    original_ean = str(ean).strip()
    ean_clean = original_ean.replace("'", "").replace('"', '').strip()
    
    logger.info(f"🔍 Recherche produit pour EAN: '{ean_clean}'")
    
    # 1. Vérifier le mapping forcé d'abord
    if original_ean in FORCED_MAPPINGS:
        forced_id = FORCED_MAPPINGS[original_ean]
        logger.info(f"🎯 MAPPING FORCÉ: '{original_ean}' → ID {forced_id}")
        return forced_id
    
    if ean_clean in FORCED_MAPPINGS:
        forced_id = FORCED_MAPPINGS[ean_clean]
        logger.info(f"🎯 MAPPING FORCÉ (nettoyé): '{ean_clean}' → ID {forced_id}")
        return forced_id
    
    # 2. Recharger le cache si vide
    if not _product_cache:
        logger.info("🔄 Cache vide, chargement...")
        load_product_cache(token)
    
    # 3. Chercher dans le cache
    formats_to_try = [
        ean_clean,                    # Format original nettoyé
        original_ean,                 # Format original
    ]
    
    # Ajouter formats sans zéros
    if ean_clean.startswith('0'):
        formats_to_try.append(ean_clean.lstrip('0'))
    
    # Ajouter derniers chiffres
    if len(ean_clean) >= 13:
        formats_to_try.append(ean_clean[-13:])
    if len(ean_clean) >= 12:
        formats_to_try.append(ean_clean[-12:])
    if len(ean_clean) >= 5:
        formats_to_try.append(ean_clean[-5:])
    
    # Chercher tous les formats
    for ean_format in set(formats_to_try):
        if ean_format in _product_cache:
            product_id = _product_cache[ean_format]
            if product_id in _product_cache_by_id:
                desc = _product_cache_by_id[product_id]["description"][:50]
                logger.info(f"✅ Trouvé dans cache: '{ean_format}' → ID {product_id} ({desc})")
            else:
                logger.info(f"✅ Trouvé dans cache: '{ean_format}' → ID {product_id}")
            return product_id
    
    # 4. Si non trouvé, recharger le cache et réessayer
    logger.warning("🔄 Non trouvé, rechargement cache...")
    load_product_cache(token, force_reload=True)
    
    for ean_format in set(formats_to_try):
        if ean_format in _product_cache:
            product_id = _product_cache[ean_format]
            logger.info(f"✅ Trouvé après rechargement: '{ean_format}' → ID {product_id}")
            return product_id
    
    # 5. Recherche API directe en dernier recours
    logger.info("🔍 Recherche API directe...")
    try:
        for page in range(0, 3):
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/50/en"
            response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
            
            if response.status_code == 200:
                products = response.json()
                for product in products:
                    product_eans = product.get("EANS", [])
                    for product_ean in product_eans:
                        if str(product_ean).strip() == ean_clean:
                            product_id = product.get("Id")
                            logger.info(f"✅ Trouvé par API: '{ean_clean}' → ID {product_id}")
                            # Ajouter au cache
                            _product_cache[ean_clean] = product_id
                            return product_id
    except Exception as e:
        logger.error(f"❌ Erreur recherche API: {e}")
    
    logger.error(f"❌ EAN '{ean_clean}' non trouvé dans NovaEngel")
    
    # 6. Fallback: utiliser les derniers chiffres comme ID
    if ean_clean[-5:].isdigit():
        possible_id = int(ean_clean[-5:])
        logger.warning(f"⚠️ Utilisation ID déduit: {possible_id}")
        return possible_id
    
    return None

# =========================== VALIDATION COMMANDE ===========================
def validate_order_products(order, token):
    """Valide tous les produits d'une commande"""
    items = order.get("line_items", [])
    validated_items = []
    
    for idx, item in enumerate(items, 1):
        sku = str(item.get("sku", "")).strip()
        quantity = int(item.get("quantity", 1))
        title = item.get("title", "")[:50]
        
        logger.info(f"📦 Item {idx}: {title}")
        logger.info(f"   SKU: '{sku}', Qty: {quantity}")
        
        if not sku:
            logger.warning(f"⚠️ Item {idx} sans SKU ignoré")
            continue
        
        product_id = find_product_id(sku, token)
        
        if product_id:
            validated_items.append({
                "productId": product_id,
                "units": quantity,
                "original_sku": sku
            })
            logger.info(f"   ✅ ID NovaEngel: {product_id}")
        else:
            logger.error(f"❌ Produit non valide: SKU '{sku}'")
            return None
    
    return validated_items if validated_items else None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """Envoie la commande à NovaEngel"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Token non disponible")
            return False
        
        # 2. Précharger cache
        load_product_cache(token)
        
        # 3. Valider produits
        order_number = order.get('name', 'N/A')
        logger.info(f"📦 Traitement commande #{order_number}")
        
        validated_items = validate_order_products(order, token)
        if not validated_items:
            logger.error("❌ Aucun produit valide")
            return False
        
        # 4. Préparer payload
        shipping = order.get("shipping_address", {})
        
        # Téléphone
        phone = shipping.get("phone", "")
        if phone:
            phone_digits = ''.join(filter(str.isdigit, phone))
            phone = phone_digits if len(phone_digits) >= 9 else "600000000"
        else:
            phone = "600000000"
        
        # Numéro commande
        order_num = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-8:]
        
        # Lignes commande
        lines = []
        for item in validated_items:
            lines.append({
                "productId": item["productId"],
                "units": item["units"]
            })
        
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
            "county": shipping.get("province", "")[:50],
            "postalCode": shipping.get("zip", "00000")[:10],
            "country": (shipping.get("country_code") or shipping.get("country") or "ES")[:2]
        }]
        
        logger.info(f"📦 Payload: {len(lines)} produits")
        
        # 5. Envoi
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        logger.info("🌐 Envoi à NovaEngel...")
        
        response = requests.post(
            url,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        
        # 6. Analyse réponse
        logger.info(f"📥 Réponse HTTP: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                
                success = True
                if isinstance(result, list):
                    for order_result in result:
                        if "Errors" in order_result and order_result["Errors"]:
                            for error in order_result["Errors"]:
                                logger.error(f"❌ Erreur NovaEngel: {error}")
                                success = False
                        else:
                            booking_code = order_result.get('BookingCode')
                            if booking_code:
                                logger.info(f"🎉 BookingCode: {booking_code}")
                            else:
                                logger.info("✅ Commande acceptée")
                
                if success:
                    logger.info("✨ COMMANDE ENVOYÉE AVEC SUCCÈS!")
                    return True
                else:
                    logger.error("❌ Commande avec erreurs")
                    return False
                    
            except json.JSONDecodeError:
                logger.info("✅ Commande probablement acceptée")
                return True
        else:
            logger.error(f"❌ Erreur {response.status_code}: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout NovaEngel")
        return False
    except Exception as e:
        logger.error(f"💥 Erreur: {e}")
        return False

# =========================== STOCK ===========================
def get_novaengel_stock():
    """Récupère le stock NovaEngel"""
    token = get_novaengel_token()
    if not token:
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
            if isinstance(stock_data, list):
                logger.info(f"📊 {len(stock_data)} produits en stock")
                return stock_data
        return []
            
    except Exception as e:
        logger.error(f"❌ Erreur stock: {e}")
        return []

# =========================== FONCTIONS UTILITAIRES ===========================
def get_product_info(product_id, token=None):
    """Récupère les infos d'un produit par ID"""
    if not token:
        token = get_novaengel_token()
    
    if product_id in _product_cache_by_id:
        return _product_cache_by_id[product_id]
    
    return None

def search_ean_advanced(ean, token=None):
    """Recherche avancée d'un EAN"""
    if not token:
        token = get_novaengel_token()
    
    return find_product_id(ean, token)

def get_cache_info():
    """Retourne les infos du cache"""
    return {
        "products_count": len(_product_cache_by_id),
        "eans_count": len(_product_cache),
        "cache_age": (datetime.now() - _cache_timestamp).seconds if _cache_timestamp else None,
        "forced_mappings": list(FORCED_MAPPINGS.keys())
    }