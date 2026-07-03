import requests
import os
import re
import logging

BASE_URL = "https://drop.novaengel.com/api"

USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]


# ==========================================
# HELPERS
# ==========================================

def normalize_country(code):
    """
    Nova requires ISO country codes.
    Shopify already provides them.
    Example: US, FR, ES, DE...
    """
    if not code:
        return ""

    return code.strip().upper()


def clean_phone(phone):
    """
    Keep only digits.
    """
    if not phone:
        return ""

    return re.sub(r"\D", "", str(phone))


def clean_text(text, max_length=100):
    if not text:
        return ""

    return str(text).strip()[:max_length]


def numeric_order_number(name):
    """
    Nova only accepts numeric order numbers
    with a maximum length of 15 digits.
    """

    number = re.sub(r"\D", "", str(name))

    if not number:
        raise Exception(
            f"Invalid order number: {name}"
        )

    return number[-15:]


# ==========================================
# LOGIN
# ==========================================

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


# ==========================================
# STOCK
# ==========================================

def get_stock(token):

    r = requests.get(
        f"{BASE_URL}/stock/update/{token}",
        timeout=60
    )

    r.raise_for_status()

    data = r.json()

    return {
        str(p.get("Id")).strip():
        int(p.get("Stock", 0))

        for p in data

        if p.get("Id") is not None
    }


# ==========================================
# SEND ORDER
# ==========================================

def send_order_to_novaengel(order):

    try:

        token = login()

        stock = get_stock(token)

        logging.info(
            f"📦 Nova stock loaded: {len(stock)} items"
        )

        lines = []

        for item in order.get("line_items", []):

            sku = (
                item.get("sku") or ""
            ).strip()

            title = item.get("title", "")

            logging.info(
                f"🔎 ITEM: {sku} | {title}"
            )

            # Empty SKU
            if not sku:

                logging.warning(
                    "⚠️ Empty SKU skipped"
                )

                continue

            # Service products
            if item.get("product_id") is None:

                logging.warning(
                    f"⚠️ Service product skipped: {sku}"
                )

                continue

            # Unknown SKU
            if sku not in stock:

                logging.warning(
                    f"❌ SKU not found in Nova: {sku}"
                )

                continue

            # Out of stock
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

                continue

        if not lines:

            logging.error(
                "❌ No valid products found"
            )

            return {
                "status": "no_valid_items"
            }

        # ==================================
        # SHIPPING ADDRESS
        # ==================================

        shipping = (
            order.get("shipping_address")
            or order.get("billing_address")
        )

        if not shipping:

            raise Exception(
                "Missing shipping address"
            )

        country = normalize_country(
            shipping.get(
                "country_code",
                ""
            )
        )

        phone = clean_phone(
            shipping.get("phone", "")
        )

        street = (
            f"{shipping.get('address1', '')} "
            f"{shipping.get('address2', '')}"
        ).strip()

        payload = [{

            "orderNumber":
                numeric_order_number(
                    order.get("name", "")
                ),

            "valoration": 0,

            "carrierNotes": "",

            "lines": lines,

            "name":
                clean_text(
                    shipping.get(
                        "first_name", ""
                    ),
                    50
                ),

            "secondName":
                clean_text(
                    shipping.get(
                        "last_name", ""
                    ),
                    50
                ),

            "telephone":
                phone,

            "mobile":
                phone,

            "street":
                clean_text(
                    street,
                    120
                ),

            "city":
                clean_text(
                    shipping.get(
                        "city", ""
                    ),
                    50
                ),

            "county":
                clean_text(
                    shipping.get(
                        "province", ""
                    ),
                    50
                ),

            "postalCode":
                clean_text(
                    shipping.get(
                        "zip", ""
                    ).replace(" ", ""),
                    20
                ),

            "country":
                country
        }]

        logging.info(
            f"🌍 Country sent: {country}"
        )

        logging.info(
            f"🚀 Sending to Nova: {payload}"
        )

        r = requests.post(
            f"{BASE_URL}/orders/sendv2/{token}",
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json"
            },
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

        # Business error returned by Nova

        if (
            isinstance(result, list)
            and len(result) > 0
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
