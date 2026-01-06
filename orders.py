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
        logger.info("🔑 Tentative d'obtention du token NovaEngel...")
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
                logger.info("✅ Token NovaEngel obtenu avec succès")
                return token
            else:
                logger.error("❌ Token non trouvé dans la réponse NovaEngel")
                logger.error(f"Réponse complète: {data}")
        else:
            logger.error(f"❌ Erreur login NovaEngel (HTTP {response.status_code}): {response.text}")
        
        return None
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de la connexion à NovaEngel")
        return None
    except Exception as e:
        logger.error(f"❌ Exception lors du login NovaEngel: {e}")
        return None

# =========================== RECHERCHE PRODUIT ===========================
def load_product_cache(token):
    """Charge les produits en cache"""
    global _product_cache, _cache_timestamp
    
    # Vérifier si le cache est encore valide
    if _cache_timestamp and (datetime.now() - _cache_timestamp).seconds < CACHE_DURATION:
        return _product_cache
    
    logger.info("📚 Chargement du cache produits NovaEngel...")
    
    try:
        cache = {}
        page = 0
        total_loaded = 0
        
        # Charger 200 produits maximum pour rapidité
        while total_loaded < 500:  # Augmenté à 500 pour plus de couverture
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/50/en"
            logger.debug(f"📖 Chargement page {page}: {url}")
            
            response = requests.get(
                url,
                headers={"Accept": "application/json"},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur chargement page {page}: HTTP {response.status_code}")
                break
            
            products = response.json()
            if not products:
                logger.info("📖 Fin des produits")
                break
            
            # Ajouter au cache
            products_added = 0
            for product in products:
                product_id = product.get("Id")
                if not product_id:
                    continue
                    
                eans = product.get("EANS", [])
                description = product.get("Description", "")[:50]
                
                for ean in eans:
                    if ean:
                        # Nettoyer l'EAN
                        ean_clean = str(ean).strip().replace("'", "").replace('"', '')
                        if ean_clean and len(ean_clean) >= 8:  # Minimum 8 chiffres pour un EAN
                            # Stocker avec l'ID comme entier
                            cache[ean_clean] = int(product_id)
                            products_added += 1
            
            total_loaded += len(products)
            logger.info(f"📖 Page {page}: {len(products)} produits, {products_added} EANs ajoutés")
            
            if len(products) < 50:
                logger.info("📖 Dernière page atteinte")
                break
            
            page += 1
            time.sleep(0.5)  # Pause pour éviter de surcharger l'API
        
        _product_cache = cache
        _cache_timestamp = datetime.now()
        
        logger.info(f"✅ Cache chargé: {total_loaded} produits, {len(cache)} EANs uniques")
        
        # Log spécifique pour BYPHASSE
        byphasse_ean = "8436097094189"
        if byphasse_ean in cache:
            logger.info(f"🎯 BYPHASSE trouvé: {byphasse_ean} → ID {cache[byphasse_ean]}")
        else:
            logger.warning(f"⚠️ BYPHASSE non trouvé dans le cache: {byphasse_ean}")
        
        return cache
        
    except Exception as e:
        logger.error(f"❌ Erreur chargement cache: {e}")
        return {}

def find_product_id(ean, token):
    """Trouve l'ID produit pour un EAN"""
    global _product_cache
    
    # Nettoyer l'EAN
    ean_clean = str(ean).strip().replace("'", "").replace('"', '')
    
    logger.info(f"🔍 Recherche ID pour EAN: '{ean_clean}'")
    
    # Vérification spéciale pour BYPHASSE
    if ean_clean == "8436097094189":
        logger.info("🎯 EAN BYPHASSE détecté")
    
    # Recharger le cache si nécessaire
    if not _product_cache:
        logger.info("🔄 Cache vide, rechargement...")
        load_product_cache(token)
    
    # Chercher dans le cache
    if ean_clean in _product_cache:
        product_id = _product_cache[ean_clean]
        logger.info(f"✅ EAN trouvé dans le cache: '{ean_clean}' → ID {product_id}")
        return product_id
    
    # Si pas dans le cache, chercher directement avec une recherche plus agressive
    logger.warning(f"⚠️ EAN '{ean_clean}' non trouvé dans le cache, recherche directe...")
    
    try:
        # Recherche sur plusieurs pages
        for page in range(0, 10):  # Jusqu'à 500 produits
            url = f"https://drop.novaengel.com/api/products/paging/{token}/{page}/50/en"
            
            response = requests.get(
                url, 
                headers={"Accept": "application/json"}, 
                timeout=20
            )
            
            if response.status_code != 200:
                logger.error(f"❌ Erreur recherche page {page}: HTTP {response.status_code}")
                continue
            
            products = response.json()
            if not products:
                break
            
            # Chercher dans cette page
            for product in products:
                eans = product.get("EANS", [])
                product_id = product.get("Id")
                description = product.get("Description", "")[:50]
                
                for e in eans:
                    if str(e).strip() == ean_clean:
                        # Ajouter au cache
                        _product_cache[ean_clean] = product_id
                        logger.info(f"✅ EAN trouvé directement: '{ean_clean}' → ID {product_id} ({description})")
                        return product_id
            
            # Si on a cherché dans 50 produits et qu'on ne l'a pas trouvé
            if page == 0:
                logger.info(f"🔍 Recherche parmi {len(products)} produits...")
            
            if len(products) < 50:
                break
        
        # Si toujours pas trouvé, essayer avec recherche exacte par code
        logger.info(f"🔄 Tentative de recherche alternative pour '{ean_clean}'...")
        
        # Nettoyer pour code produit (derniers chiffres)
        if len(ean_clean) >= 5:
            possible_code = ean_clean[-5:]  # Derniers 5 chiffres
            logger.info(f"🔍 Recherche par code possible: {possible_code}")
            
            # Vérifier si c'est un code numérique
            if possible_code.isdigit():
                code_int = int(possible_code)
                # Chercher dans le cache pour correspondance partielle
                for cached_ean, cached_id in _product_cache.items():
                    if str(cached_id) == possible_code:
                        logger.info(f"✅ Correspondance trouvée: EAN {cached_ean} → ID {cached_id}")
                        return cached_id
        
        logger.error(f"❌ EAN '{ean_clean}' non trouvé dans NovaEngel")
        return None
        
    except Exception as e:
        logger.error(f"❌ Erreur recherche produit: {e}")
        return None

# =========================== ENVOI COMMANDE ===========================
def send_order_to_novaengel(order):
    """ENVOIE la commande à NovaEngel"""
    logger.info("🚀 DÉBUT ENVOI COMMANDE NOVAENGEL")
    
    try:
        # 1. Token
        token = get_novaengel_token()
        if not token:
            logger.error("❌ Impossible d'obtenir le token NovaEngel")
            return False
        
        # 2. Recharger le cache avant de traiter
        load_product_cache(token)
        
        # 3. Préparer les lignes de commande
        lines = []
        items = order.get("line_items", [])
        order_number = order.get('name', 'N/A')
        
        logger.info(f"📦 Traitement commande #{order_number} - {len(items)} items")
        
        for idx, item in enumerate(items, 1):
            ean = str(item.get("sku", "")).strip()
            quantity = int(item.get("quantity", 1))
            product_title = item.get("title", "")[:50]
            
            if not ean:
                logger.warning(f"⚠️ Item {idx} sans EAN/SKU ignoré: {product_title}")
                continue
            
            logger.info(f"📦 Item {idx}: {product_title}")
            logger.info(f"   EAN/SKU: '{ean}', Quantité: {quantity}")
            
            # Chercher l'ID produit
            product_id = find_product_id(ean, token)
            
            if product_id:
                lines.append({
                    "productId": product_id,
                    "units": quantity
                })
                logger.info(f"   ✅ ID trouvé: {product_id}")
            else:
                # Si l'EAN n'est pas trouvé, essayer avec les derniers chiffres
                ean_clean = ean.replace("'", "").replace('"', '').strip()
                if len(ean_clean) >= 5 and ean_clean[-5:].isdigit():
                    possible_id = int(ean_clean[-5:])
                    logger.info(f"   ⚠️ Tentative avec code produit: {possible_id}")
                    lines.append({
                        "productId": possible_id,
                        "units": quantity
                    })
                    logger.info(f"   ⚠️ Utilisation ID déduit: {possible_id}")
                else:
                    logger.error(f"   ❌ EAN '{ean}' non trouvé et impossible de déduire l'ID")
                    return False  # Arrêter si un produit crucial n'est pas trouvé
        
        if not lines:
            logger.error("❌ Aucun produit valide trouvé pour la commande")
            return False
        
        # 4. Préparer l'adresse
        shipping = order.get("shipping_address", {})
        
        # Nettoyer le téléphone
        phone = shipping.get("phone", "")
        if phone:
            # Garder seulement les chiffres
            phone = ''.join(filter(str.isdigit, phone))
            if len(phone) < 9:
                phone = "600000000"  # Téléphone par défaut
        
        # 5. Numéro de commande (doit être numérique pour NovaEngel)
        order_num = order.get("name", "").replace("#", "").replace("TEST", "").replace("ORD", "")
        if not order_num.isdigit():
            order_num = str(int(time.time()))[-8:]
            logger.info(f"📝 Numéro de commande généré: {order_num}")
        
        # 6. PAYLOAD FINAL
        payload = [{
            "orderNumber": order_num[:15],
            "valoration": 0.0,
            "carrierNotes": f"Commande Shopify #{order.get('name', order_num)}",
            "lines": lines,
            "name": shipping.get("first_name", "Client")[:50],
            "secondName": shipping.get("last_name", "")[:50],
            "telephone": phone[:15] or "600000000",
            "mobile": phone[:15] or "600000000",
            "street": shipping.get("address1", "Adresse non spécifiée")[:100],
            "city": shipping.get("city", "Ville inconnue")[:50],
            "county": shipping.get("province", "")[:50],
            "postalCode": shipping.get("zip", "00000")[:10],
            "country": (shipping.get("country_code") or shipping.get("country") or "ES")[:2]
        }]
        
        logger.info(f"📦 Payload prêt pour commande #{order_num}")
        logger.info(f"📋 Contenu: {len(lines)} produits")
        logger.info(f"🏠 Adresse: {shipping.get('first_name', '')} {shipping.get('last_name', '')}")
        logger.info(f"📍 Ville: {shipping.get('city', '')} {shipping.get('zip', '')}")
        
        # 7. ENVOYER À NOVAENGEL
        url = f"https://drop.novaengel.com/api/orders/sendv2/{token}"
        logger.info(f"🌐 Envoi à NovaEngel: {url}")
        
        # Debug: Afficher le payload
        logger.debug(f"📄 Payload JSON: {json.dumps(payload, indent=2)}")
        
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
        logger.info(f"📥 Réponse NovaEngel: HTTP {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info("✅ Réponse JSON NovaEngel reçue")
                
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
                            logger.info(f"🎉 BookingCode: {booking_code or 'Non fourni'}")
                            logger.info(f"💬 Message: {message or 'Succès'}")
                
                if success:
                    logger.info("✨ COMMANDE ENVOYÉE AVEC SUCCÈS À NOVAENGEL!")
                    return True
                else:
                    logger.error("❌ Commande NovaEngel avec erreurs")
                    return False
                
            except json.JSONDecodeError:
                logger.info(f"📝 Réponse texte (non-JSON): {response.text[:200]}")
                # Même si ce n'est pas du JSON, un 200 est généralement bon
                logger.info("✅ Commande probablement acceptée (HTTP 200)")
                return True
                
        elif response.status_code == 400:
            logger.error(f"❌ Erreur 400 - Requête incorrecte: {response.text[:500]}")
            return False
        elif response.status_code == 401:
            logger.error("❌ Erreur 401 - Token invalide ou expiré")
            return False
        elif response.status_code == 500:
            logger.error(f"❌ Erreur 500 - Erreur serveur NovaEngel: {response.text[:500]}")
            return False
        else:
            logger.error(f"❌ Erreur {response.status_code}: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de l'envoi à NovaEngel")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur réseau NovaEngel: {e}")
        return False
    except Exception as e:
        logger.error(f"💥 Exception inattendue lors de l'envoi: {e}")
        return False

# =========================== STOCK ===========================
def get_novaengel_stock():
    """Récupère le stock NovaEngel"""
    token = get_novaengel_token()
    if not token:
        logger.error("❌ Pas de token pour récupérer le stock")
        return []
    
    try:
        url = f"https://drop.novaengel.com/api/stock/update/{token}"
        logger.info("📊 Récupération du stock NovaEngel...")
        
        response = requests.get(
            url,
            headers={"Accept": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            stock_data = response.json()
            if isinstance(stock_data, list):
                logger.info(f"📊 Stock récupéré: {len(stock_data)} produits")
                
                # Log quelques produits pour vérification
                for i, product in enumerate(stock_data[:3]):
                    product_id = product.get("Id", "N/A")
                    stock = product.get("Stock", 0)
                    logger.debug(f"   Produit {i+1}: ID {product_id}, Stock {stock}")
                
                return stock_data
            else:
                logger.error(f"❌ Format de stock invalide: {type(stock_data)}")
                return []
        else:
            logger.error(f"❌ Erreur récupération stock (HTTP {response.status_code}): {response.text[:200]}")
            return []
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout lors de la récupération du stock")
        return []
    except Exception as e:
        logger.error(f"❌ Exception récupération stock: {e}")
        return []

# =========================== DEBUG FUNCTIONS ===========================
def debug_ean_search(ean):
    """Fonction de debug pour rechercher un EAN spécifique"""
    logger.info(f"🔍 DEBUG: Recherche manuelle pour EAN: {ean}")
    
    token = get_novaengel_token()
    if not token:
        return None
    
    return find_product_id(ean, token)

# Test direct si exécuté seul
if __name__ == "__main__":
    # Test rapide du token
    print("🧪 Test du module orders.py...")
    token = get_novaengel_token()
    if token:
        print(f"✅ Token obtenu: {token[:20]}...")
        
        # Test recherche BYPHASSE
        ean = "8436097094189"
        print(f"\n🔍 Test recherche EAN: {ean}")
        product_id = find_product_id(ean, token)
        print(f"📦 Résultat: ID {product_id}")
        
        # Afficher le cache
        print(f"\n📚 Cache chargé: {len(_product_cache)} EANs")
        if ean in _product_cache:
            print(f"✅ BYPHASSE dans le cache: {ean} → {_product_cache[ean]}")
    else:
        print("❌ Impossible d'obtenir le token")