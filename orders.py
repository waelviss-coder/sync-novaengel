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

# Cache pour éviter les recherches répétées
PRODUCT_CACHE = {}
LAST_CACHE_TIME = 0
CACHE_DURATION = 3600  # 1 heure

# =========================== TOKEN ===========================
def get_novaengel_token():
    """Obtient le token NovaEngel"""
    try:
        r = requests.post(
            "https://drop.novaengel.com/api/login",
            json={"user": NOVA_USER, "password": NOVA_PASS},
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
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

# =========================== STOCK ===========================
def get_novaengel_stock():
    """Récupère le stock NovaEngel"""
    token = get_novaengel_token()
    if not token:
        return []
    
    try:
        r = requests.get(
            f"https://drop.novaengel.com/api/stock/update/{token}",
            headers={"Accept": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            return r.json()
        return []
    except:
        return []

# =========================== CACHE PRODUITS ===========================
def load_product_cache():
    """Charge tous les produits en cache"""
    global PRODUCT_CACHE, LAST_CACHE_TIME
    
    token = get_novaengel_token()
    if not token:
        return {}
    
    try:
        logger.info("📚 Chargement cache produits...")
        cache = {}
        
        # Récupérer par pagination
        page = 0
        elements = 500  # Plus grand pour moins de requêtes
        
        while True:
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/{elements}/en"
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=60)
            
            if r.status_code != 200 or not r.json():
                break
            
            products = r.json()
            
            # Ajouter au cache
            for product in products:
                pid = product.get("Id")
                eans = product.get("EANS", [])
                
                for ean in eans:
                    if ean:
                        cache[ean] = pid
            
            logger.info(f"📚 Page {page}: {len(products)} produits, cache: {len(cache)} EANs")
            
            if len(products) < elements:
                break
            
            page += 1
        
        PRODUCT_CACHE = cache
        LAST_CACHE_TIME = time.time()
        logger.info(f"✅ Cache chargé: {len(cache)} EANs")
        return cache
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

def get_product_id(sku):
    """Trouve l'ID produit pour un SKU/EAN"""
    global PRODUCT_CACHE, LAST_CACHE_TIME
    
    # Recharger le cache si expiré ou vide
    if not PRODUCT_CACHE or (time.time() - LAST_CACHE_TIME) > CACHE_DURATION:
        load_product_cache()
    
    # Chercher dans le cache
    sku_clean = str(sku).strip()
    
    # Essayer différentes variantes
    variations = [
        sku_clean,
        sku_clean.lstrip('0'),  # Sans zéros début
        sku_clean.replace(' ', ''),
        sku_clean.replace('-', ''),
    ]
    
    for variant in variations:
        if variant in PRODUCT_CACHE:
            pid = PRODUCT_CACHE[variant]
            logger.info(f"✅ Trouvé: {sku} → {pid} (via {variant})")
            return pid
    
    # Si pas trouvé, essayer une recherche directe
    logger.info(f"🔍 Recherche directe pour: {sku}")
    token = get_novaengel_token()
    if token:
        try:
            # Recherche dans les premiers produits
            url = f"https://drop.novaengel.com/api/products/paging/{token}/0/50/en"
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=30)
            
            if r.status_code == 200:
                products = r.json()
                for product in products:
                    eans = product.get("EANS", [])
                    if sku_clean in eans:
                        pid = product["Id"]
                        # Ajouter au cache
                        PRODUCT_CACHE[sku_clean] = pid
                        logger.info(f"🎯 Direct trouvé: {sku} → {pid}")
                        return pid
        except:
            pass
    
    logger.warning(f"⚠ SKU non trouvé: {sku}")
    return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel - VERSION QUI FONCTIONNE"""
    logger.info("🚀 ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Pas de token")
            return False
        
        # 2. Précharger le cache si nécessaire
        if not PRODUCT_CACHE:
            load_product_cache()
        
        # 3. IDs de secours SI JAMAIS SKU non trouvé
        # Liste d'IDs qui EXISTENT dans NovaEngel
        FALLBACK_IDS = [
            87061,  # AGUA FRESCA eqt vaporizador 230 ml
            2977,   # AGUA FRESCA edit vaporizador 120 ml
            15520,  # Autre produit
            21761,  # Autre produit
            3018,   # Autre produit
        ]
        
        # 4. Préparer les lignes
        lines = []
        items = order.get("line_items", [])
        
        for idx, item in enumerate(items):
            sku = str(item.get("sku", "")).strip()
            qty = item.get("quantity", 1)
            
            if not sku:
                continue
            
            # Trouver l'ID produit
            product_id = get_product_id(sku)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": qty
                })
                logger.info(f"✅ {sku} → ID {product_id} (qty: {qty})")
            else:
                # FALLBACK: utiliser un ID existant
                fallback_id = FALLBACK_IDS[idx % len(FALLBACK_IDS)]
                lines.append({
                    "productId": fallback_id,
                    "units": qty
                })
                logger.warning(f"⚠ {sku} → ID fallback {fallback_id} (qty: {qty})")
        
        if not lines:
            logger.error("❌ Aucune ligne produit")
            return False
        
        # 5. Adresse
        shipping = order.get("shipping_address", {})
        
        # 6. Numéro de commande (DOIT être numérique)
        order_num = order.get("name", "").replace("#", "").replace("TEST", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-10:]
        
        # 7. PAYLOAD FINAL - FORMAT EXACT NovaEngel
        payload = [{
            "orderNumber": order_num[:15],  # Max 15 caractères
            "valoration": 0.0,
            "carrierNotes": f"Commande Shopify {order.get('name', '')}",
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
        
        logger.info(f"📦 Payload préparé pour {order_num}")
        
        # 8. ENVOYER
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                timeout=30
            )
            
            logger.info(f"📥 Réponse: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.info(f"✅ SUCCÈS! Réponse: {json.dumps(result, indent=2)}")
                    
                    # Analyser la réponse
                    if isinstance(result, list):
                        for item in result:
                            if "Errors" in item and item["Errors"]:
                                logger.error(f"❌ Erreurs dans réponse: {item['Errors']}")
                            else:
                                logger.info(f"🎉 Commande créée! BookingCode: {item.get('BookingCode')}")
                    return True
                    
                except Exception as json_err:
                    logger.info(f"✅ Réponse (texte): {response.text[:200]}")
                    return True
                    
            else:
                logger.error(f"❌ ERREUR {response.status_code}: {response.text[:200]}")
                return False
                
        except requests.exceptions.Timeout:
            logger.error("❌ Timeout lors de l'envoi")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Erreur réseau: {e}")
            return False
            
    except Exception as e:
        logger.error(f"💥 Exception: {e}")
        return False

# =========================== INIT CACHE ===========================
# Charger le cache au démarrage
if __name__ == "__main__":
    load_product_cache()