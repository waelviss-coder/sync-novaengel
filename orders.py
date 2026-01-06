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

# =========================== MAPPING EAN → ID ===========================
# ⚠️ REMPLISSEZ CE DICTIONNAIRE AVEC VOS VRAIS EANs ET IDs
# Format: "VOTRE_EAN": ID_NOVAENGEL
EAN_TO_ID_MAPPING = {
    # ==== EXEMPLES - À REMPLACER ====
    "8436097094189": 94189,    # BYPHASSE - MOISTURIZING LIP BALM
    "8410190613430": 87061,    # SHISEIDO - SYNCHRO SKIN
    "841819825448": 2977,      # Exemple
    "841819881138": 3018,      # Exemple
    "0729238187061": 87061,    # Autre EAN pour SHISEIDO
    # ==== AJOUTEZ VOS EANs ICI ====
}

# Cache pour éviter recherches répétées
_product_cache = {}
_cache_expiry = None
CACHE_DURATION = 3600  # 1 heure

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient un token NovaEngel"""
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
                logger.info(f"🔑 Token obtenu: {token[:8]}...")
                return token
            else:
                logger.error("❌ Token non trouvé dans la réponse")
        else:
            logger.error(f"❌ Erreur login: {response.status_code}")
        
        return None
    except Exception as e:
        logger.error(f"❌ Exception login: {e}")
        return None

# =========================== CHARGEMENT PRODUITS ===========================
def load_products_cache():
    """Charge tous les produits en cache (une seule fois)"""
    global _product_cache, _cache_expiry
    
    # Si cache valide, retourner
    if _product_cache and _cache_expiry and datetime.now() < _cache_expiry:
        return _product_cache
    
    token = get_novaengel_token()
    if not token:
        return {}
    
    logger.info("📚 Chargement des produits NovaEngel...")
    
    try:
        cache = {}
        page = 0
        total_products = 0
        
        while True:
            # Récupérer par pages de 200
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/200/en"
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur page {page}: {response.status_code}")
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
                        cache[ean] = product_id
            
            total_products += len(products)
            logger.info(f"📖 Page {page}: {len(products)} produits")
            
            # Si moins de produits que demandé, fini
            if len(products) < 200:
                break
            
            page += 1
        
        _product_cache = cache
        _cache_expiry = datetime.now() + timedelta(seconds=CACHE_DURATION)
        
        logger.info(f"✅ Cache chargé: {total_products} produits, {len(cache)} EANs")
        
        # Afficher les premiers EANs pour vérification
        if cache:
            sample = list(cache.items())[:5]
            logger.info("📋 Exemple EANs → IDs:")
            for ean, pid in sample:
                logger.info(f"  {ean} → {pid}")
        
        return cache
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

# =========================== RECHERCHE ID PRODUIT ===========================
def find_product_id(ean):
    """Trouve l'ID produit pour un EAN"""
    # 1. Chercher dans le mapping manuel (priorité)
    if ean in EAN_TO_ID_MAPPING:
        logger.info(f"✅ Mapping manuel: {ean} → {EAN_TO_ID_MAPPING[ean]}")
        return EAN_TO_ID_MAPPING[ean]
    
    # 2. Charger le cache si nécessaire
    if not _product_cache:
        load_products_cache()
    
    # 3. Chercher dans le cache
    ean_clean = str(ean).strip()
    
    # Essayer différentes variantes
    variations = [
        ean_clean,
        ean_clean.lstrip('0'),
        ean_clean.replace(' ', ''),
        ean_clean.replace('-', ''),
    ]
    
    for variant in variations:
        if variant in _product_cache:
            pid = _product_cache[variant]
            logger.info(f"✅ Trouvé dans cache: {ean} → {pid}")
            return pid
    
    logger.warning(f"⚠️ EAN non trouvé: {ean}")
    return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel - VERSION FINALE"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Impossible d'obtenir le token")
            return False
        
        # 2. Précharger le cache des produits
        load_products_cache()
        
        # 3. Préparer les lignes de commande
        lines = []
        items = order.get("line_items", [])
        
        for item in items:
            ean = str(item.get("sku", "")).strip()
            quantity = item.get("quantity", 1)
            
            if not ean:
                logger.warning("⚠️ Item sans EAN ignoré")
                continue
            
            # Trouver l'ID produit
            product_id = find_product_id(ean)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"✅ {ean} → ID {product_id} (qty: {quantity})")
            else:
                logger.error(f"❌ EAN non trouvé: {ean} - item ignoré")
                # Continuer avec les autres items
        
        if not lines:
            logger.error("❌ Aucun produit valide dans la commande")
            return False
        
        # 4. Préparer l'adresse
        shipping = order.get("shipping_address", {})
        
        # 5. Numéro de commande (DOIT être numérique)
        order_number = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_number.isdigit():
            order_number = str(int(time.time()))[-10:]
            logger.info(f"📝 Numéro généré: {order_number}")
        
        # 6. PAYLOAD FINAL - Format exact NovaEngel
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
        
        # 7. ENVOYER À NOVAENGEL
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        logger.info(f"🌐 Envoi à: {url}")
        
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
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"✅ SUCCÈS! Réponse complète:")
                logger.info(json.dumps(result, indent=2))
                
                # Vérifier les erreurs détaillées
                if isinstance(result, list):
                    for order_result in result:
                        if "Errors" in order_result and order_result["Errors"]:
                            for error in order_result["Errors"]:
                                logger.error(f"❌ Erreur: {error}")
                        else:
                            logger.info(f"🎉 Commande traitée! BookingCode: {order_result.get('BookingCode', 'N/A')}")
                
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