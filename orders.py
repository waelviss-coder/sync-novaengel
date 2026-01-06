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

# Cache optimisé
_product_cache = {}
_product_cache_by_id = {}  # Nouveau cache par ID
_cache_timestamp = None
CACHE_DURATION = 300

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient le token NovaEngel"""
    try:
        logger.info("🔑 Connexion à NovaEngel...")
        response = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("Token") or data.get("token")
            if token:
                logger.info("✅ Token NovaEngel obtenu")
                return token
            else:
                logger.error("❌ Token non trouvé dans la réponse")
        else:
            logger.error(f"❌ Erreur login NovaEngel: {response.status_code}")
        
        return None
    except Exception as e:
        logger.error(f"❌ Exception login NovaEngel: {e}")
        return None

# =========================== CACHE PRODUITS ===========================
def load_product_cache(token, force_reload=False):
    """Charge tous les produits NovaEngel en cache"""
    global _product_cache, _product_cache_by_id, _cache_timestamp
    
    # Vérifier cache valide
    if not force_reload and _cache_timestamp and (datetime.now() - _cache_timestamp).seconds < CACHE_DURATION:
        logger.info("📚 Cache produits déjà à jour")
        return _product_cache
    
    logger.info("🔄 Chargement complet du cache produits NovaEngel...")
    
    try:
        cache_by_ean = {}
        cache_by_id = {}
        page = 0
        total_products = 0
        found_byphasse = False
        
        # Charger toutes les pages
        while True:
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/100/en"
            
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur page {page}: HTTP {response.status_code}")
                break
            
            products = response.json()
            if not products:
                break
            
            for product in products:
                product_id = product.get("Id")
                if not product_id:
                    continue
                
                description = product.get("Description", "")
                eans = product.get("EANS", [])
                sku = product.get("SKU", "")
                full_code = product.get("FullCode", "")
                
                # Stocker dans cache par ID
                cache_by_id[product_id] = {
                    "description": description,
                    "eans": eans,
                    "sku": sku,
                    "full_code": full_code
                }
                
                # Ajouter tous les EANs au cache
                for ean in eans:
                    if ean:
                        ean_str = str(ean).strip()
                        # Format original
                        cache_by_ean[ean_str] = product_id
                        
                        # Formats alternatifs
                        if ean_str.startswith('0'):
                            # Sans zéros au début
                            cache_by_ean[ean_str.lstrip('0')] = product_id
                        
                        # Derniers chiffres
                        if len(ean_str) > 5:
                            cache_by_ean[ean_str[-5:]] = product_id
                
                # BYPHASSE spécifique
                if "BYPHASSE" in description.upper() and "8436097094189" in str(eans):
                    logger.info(f"🎯 BYPHASSE trouvé: ID {product_id}")
                    found_byphasse = True
                
                total_products += 1
            
            logger.info(f"📖 Page {page}: {len(products)} produits")
            
            if len(products) < 100:
                break
            
            page += 1
            time.sleep(0.3)  # Pause pour éviter rate limit
        
        _product_cache = cache_by_ean
        _product_cache_by_id = cache_by_id
        _cache_timestamp = datetime.now()
        
        logger.info(f"✅ Cache chargé: {total_products} produits, {len(cache_by_ean)} références EAN")
        
        if found_byphasse:
            logger.info("✅ BYPHASSE correctement indexé dans le cache")
        else:
            logger.warning("⚠️ BYPHASSE non trouvé dans le cache")
        
        # Debug: afficher quelques produits
        debug_count = 0
        for ean, pid in list(cache_by_ean.items())[:5]:
            if pid in cache_by_id:
                desc = cache_by_id[pid]["description"][:30]
                logger.debug(f"📦 Exemple: EAN {ean} → ID {pid} ({desc})")
                debug_count += 1
        
        return cache_by_ean
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

# =========================== RECHERCHE PRODUIT ===========================
def find_product_id(ean, token):
    """Trouve l'ID produit pour un EAN avec toutes les méthodes"""
    global _product_cache, _product_cache_by_id
    
    # Nettoyer l'EAN
    original_ean = str(ean).strip()
    ean_clean = original_ean.replace("'", "").replace('"', '').strip()
    
    logger.info(f"🔍 Recherche produit: EAN '{ean_clean}'")
    
    # Recharger le cache si vide
    if not _product_cache:
        logger.info("🔄 Cache vide, chargement initial...")
        load_product_cache(token)
    
    # Liste de tous les formats à essayer
    formats_to_try = []
    
    # Format original
    formats_to_try.append(ean_clean)
    
    # Sans apostrophe
    formats_to_try.append(ean_clean.replace("'", ""))
    
    # Sans zéros au début
    if ean_clean.startswith('0'):
        formats_to_try.append(ean_clean.lstrip('0'))
    
    # Derniers chiffres
    if len(ean_clean) > 13:
        formats_to_try.append(ean_clean[-13:])
    if len(ean_clean) > 12:
        formats_to_try.append(ean_clean[-12:])
    if len(ean_clean) > 11:
        formats_to_try.append(ean_clean[-11:])
    if len(ean_clean) >= 5:
        formats_to_try.append(ean_clean[-5:])
    
    # Forme numérique si possible
    try:
        ean_numeric = int(''.join(filter(str.isdigit, ean_clean)))
        formats_to_try.append(str(ean_numeric))
        if len(str(ean_numeric)) > 13:
            formats_to_try.append(str(ean_numeric)[-13:])
        if len(str(ean_numeric)) >= 5:
            formats_to_try.append(str(ean_numeric)[-5:])
    except:
        pass
    
    # Chercher dans le cache
    for ean_format in set(formats_to_try):  # set() pour éviter doublons
        if ean_format in _product_cache:
            product_id = _product_cache[ean_format]
            if product_id in _product_cache_by_id:
                desc = _product_cache_by_id[product_id]["description"][:40]
                logger.info(f"✅ Trouvé (format '{ean_format}'): → ID {product_id} ({desc})")
            else:
                logger.info(f"✅ Trouvé (format '{ean_format}'): → ID {product_id}")
            return product_id
    
    # BYPHASSE - solution de secours
    if "8436097094189" in ean_clean or ean_clean.endswith("094189") or ean_clean.endswith("94189"):
        logger.info(f"🎯 BYPHASSE détecté, utilisation ID 94189")
        return 94189
    
    # Si non trouvé, recharger le cache et réessayer
    logger.warning("🔄 EAN non trouvé, rechargement du cache...")
    load_product_cache(token, force_reload=True)
    
    for ean_format in set(formats_to_try):
        if ean_format in _product_cache:
            product_id = _product_cache[ean_format]
            logger.info(f"✅ Trouvé après rechargement: '{ean_format}' → ID {product_id}")
            return product_id
    
    # Recherche API directe en dernier recours
    logger.info("🔍 Recherche API directe...")
    try:
        for page in range(0, 3):  # 3 premières pages
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/50/en"
            response = requests.get(url, headers={"Accept": "application/json"}, timeout=20)
            
            if response.status_code == 200:
                products = response.json()
                for product in products:
                    product_eans = product.get("EANS", [])
                    for product_ean in product_eans:
                        if str(product_ean).strip() == ean_clean:
                            product_id = product.get("Id")
                            logger.info(f"✅ Trouvé par API directe: → ID {product_id}")
                            # Ajouter au cache
                            _product_cache[ean_clean] = product_id
                            return product_id
    except Exception as e:
        logger.error(f"❌ Erreur recherche API: {e}")
    
    logger.error(f"❌ EAN '{ean_clean}' non trouvé dans NovaEngel")
    return None

# =========================== VALIDATION COMMANDE ===========================
def validate_products_in_order(order, token):
    """Valide que tous les produits de la commande existent"""
    items = order.get("line_items", [])
    validated_items = []
    
    for item in items:
        ean = str(item.get("sku", "")).strip()
        quantity = int(item.get("quantity", 1))
        
        if not ean:
            continue
        
        product_id = find_product_id(ean, token)
        
        if product_id:
            validated_items.append({
                "productId": product_id,
                "units": quantity,
                "original_sku": ean
            })
        else:
            logger.error(f"❌ Produit non valide: SKU '{ean}'")
            return None
    
    return validated_items

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel"""
    logger.info("🚀 DÉBUT ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Token NovaEngel non disponible")
            return False
        
        # 2. Précharger le cache
        load_product_cache(token)
        
        # 3. Valider les produits
        order_number = order.get('name', 'N/A')
        logger.info(f"📦 Validation commande #{order_number}")
        
        validated_items = validate_products_in_order(order, token)
        if not validated_items:
            logger.error("❌ Aucun produit valide pour la commande")
            return False
        
        # 4. Préparer l'adresse
        shipping = order.get("shipping_address", {})
        
        # Nettoyer téléphone
        phone = shipping.get("phone", "")
        if phone:
            phone_digits = ''.join(filter(str.isdigit, phone))
            phone = phone_digits if len(phone_digits) >= 9 else "600000000"
        else:
            phone = "600000000"
        
        # 5. Numéro de commande
        order_num = order.get("name", "").replace("#", "").replace("TEST", "").replace("ORD", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-8:]
        
        # 6. Construire le payload
        lines = []
        for item in validated_items:
            lines.append({
                "productId": item["productId"],
                "units": item["units"]
            })
            logger.info(f"   ✅ {item['original_sku']} → ID {item['productId']} (qty: {item['units']})")
        
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
        
        logger.info(f"📦 Payload prêt: {len(lines)} produits")
        
        # 7. Envoi à NovaEngel
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
        
        # 8. Analyse réponse
        logger.info(f"📥 Réponse: HTTP {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info("📊 Analyse réponse JSON...")
                
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
                                logger.info(f"🎉 Commande créée: BookingCode {booking_code}")
                            else:
                                logger.info("✅ Commande acceptée")
                
                if success:
                    logger.info("✨ COMMANDE ENVOYÉE AVEC SUCCÈS!")
                    return True
                else:
                    logger.error("❌ Commande avec erreurs")
                    return False
                    
            except json.JSONDecodeError:
                logger.info(f"📝 Réponse texte: {response.text[:100]}")
                return True
        else:
            logger.error(f"❌ Erreur {response.status_code}: {response.text[:200]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout NovaEngel")
        return False
    except Exception as e:
        logger.error(f"💥 Erreur inattendue: {e}")
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
            else:
                logger.error(f"❌ Format stock invalide")
                return []
        else:
            logger.error(f"❌ Erreur stock: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"❌ Exception stock: {e}")
        return []

# =========================== FONCTIONS DEBUG ===========================
def search_product_by_ean(ean, token=None):
    """Fonction de recherche avancée pour debug"""
    if not token:
        token = get_novaengel_token()
    
    if not token:
        return None
    
    logger.info(f"🔍 RECHERCHE AVANCÉE: {ean}")
    
    # Charger cache complet
    load_product_cache(token, force_reload=True)
    
    # Chercher avec tous les formats
    product_id = find_product_id(ean, token)
    
    if product_id and product_id in _product_cache_by_id:
        product_info = _product_cache_by_id[product_id]
        logger.info(f"📦 INFOS PRODUIT:")
        logger.info(f"   ID: {product_id}")
        logger.info(f"   Description: {product_info['description']}")
        logger.info(f"   EANS: {product_info['eans']}")
        logger.info(f"   SKU: {product_info['sku']}")
        logger.info(f"   FullCode: {product_info['full_code']}")
    
    return product_id

def get_cache_stats():
    """Retourne les statistiques du cache"""
    return {
        "total_eans": len(_product_cache),
        "total_products": len(_product_cache_by_id),
        "cache_age": (datetime.now() - _cache_timestamp).seconds if _cache_timestamp else None
    }