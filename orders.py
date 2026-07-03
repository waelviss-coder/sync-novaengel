import requests
import os
import re
import logging

BASE_URL = "https://drop.novaengel.com/api"

USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]


# ====================================
# COUNTRY NORMALIZATION
# ====================================
def normalize_country(code):
    """
    Shopify already sends ISO country codes:
    US, FR, ES, DE, IT, TN...
    """
    if not code:
        return ""

    return code.strip().upper()


# ====================================
# LOGIN
# ====================================
def login():

    r = requests.post(
        f"{BASE_URL}/login",
        json={
            "user": USER,
            "password": PASS
        },
        timeout=30
    )

    r.raise_for_status()

    data = r.json()

    token = data.get("Token") or data.get("token")

    if not token:
        raise Exception("Nova token missing")

    return token


# ====================================
# LOAD STOCK
# ====================================
def get_stock(token):

    r = requests.get(
        f"{BASE_URL}/stock/update/{token}",
        timeout=60
    )

    r.raise_for_status()

    data = r.json()

    return {
        str(p["Id"]).strip(): int(p.get("Stock", 0))
        for p in data
        if p.get("Id") is not None
    }


# ====================================
# CLEAN ORDER NUMBER
# ====================================
def numeric_order_number(name):

    number = re.sub(r"\D", "", str(name))

    if not number:
        raise Exception(
            f"Invalid order number: {name}"
        )

    return number[-15:]


# ====================================
# SEND ORDER
# ====================================
def send_order_to_novaengel(order):

    try:

        token = login()

        stock = get_stock(token)

        logging.info(
            f"📦 Nova stock loaded: {len(stock)} items"
        )

        lines = []

        for item in order.get("line_items", []):

            sku = (item.get("sku") or "").strip()
            title = item.get("title", "")

            logging.info(f"🔎 ITEM: {sku} | {title}")

            # skip empty SKU
            if not sku:
                logging.warning(
                    "⚠️ Empty SKU skipped"
                )
                continue

            # skip service products
            if item.get("product_id") is None:
                logging.warning(
                    f"⚠️ Service product skipped: {sku}"
                )
                continue

            # SKU not found
            if sku not in stock:
                logging.warning(
                    f"❌ SKU not found in Nova: {sku}"
                )
                continue

            # no stock
            if stock[sku] <= 0:
                logging.warning(
                    f"⚠️ Out of stock: {sku}"
                )
                continue

            try:

                lines.append({
                    "productId": int(sku),
                    "units": int(
                        item.get("quantity", 1)
                    )
                })

            except Exception:

                logging.warning(
                    f"⚠️ Invalid SKU format: {sku}"
                )

        if not lines:

            logging.error(
                "❌ No valid products to send"
            )

            return {
                "status": "no_valid_items"
            }

        # --------------------------------
        # SHIPPING ADDRESS
        # --------------------------------

        shipping = (
            order.get("shipping_address")
            or order.get("billing_address")
        )

        if not shipping:
            raise Exception(
                "Missing shipping address"
            )

        country = normalize_country(
            shipping.get("country_code", "")
        )

        logging.info(
            f"🌍 Country sent to Nova: {country}"
        )

        payload = [{
            "orderNumber": numeric_order_number(
                order.get("name", "")
            ),

            "lines": lines,

            "name": shipping.get(
                "first_name", ""
            ),

            "secondName": shipping.get(
                "last_name", ""
            ),

            "telephone": shipping.get(
                "phone", ""
            ),

            "mobile": shipping.get(
                "phone", ""
            ),

            "street": shipping.get(
                "address1", ""
            ),

            "city": shipping.get(
                "city", ""
            ),

            "county": shipping.get(
                "province", ""
            ),

            "postalCode": shipping.get(
                "zip", ""
            ),

            "country": country
        }]

        logging.info(
            f"🚀 Sending to Nova: {payload}"
        )

        r = requests.post(
            f"{BASE_URL}/orders/sendv2/{token}",
            json=payload,
            timeout=60
        )

        logging.info(
            f"HTTP Status: {r.status_code}"
        )

        try:
            result = r.json()
        except Exception:
            result = r.text

        logging.info(
            f"📩 Nova response: {result}"
        )

        # Nova business error
        if (
            isinstance(result, list)
            and result
            and result[0].get("Message") == "KO"
        ):

            logging.error(
                f"❌ Nova rejected order: {result}"
            )

            return {
                "status": "rejected",
                "nova_error": result
            }

        return {
            "status": "success",
            "nova_response": result
        }

    except requests.exceptions.HTTPError as e:

        logging.exception(
            "❌ HTTP error"
        )

        return {
            "status": "http_error",
            "message": str(e)
        }

    except Exception as e:

        logging.exception(
            "❌ send_order_to_novaengel failed"
        )

        return {
            "status": "error",
            "message": str(e)
        }
