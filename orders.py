import requests
import os
import re
import logging

BASE_URL = "https://drop.novaengel.com/api"

USER = os.environ["NOVA_USER"]
PASS = os.environ["NOVA_PASS"]


# =========================
# COUNTRY NORMALIZATION
# =========================
COUNTRY_MAP = {
    "US": "United States",
    "CA": "Canada",
    "FR": "France",
    "TN": "Tunisia",
    "DE": "Germany",
    "GB": "United Kingdom"
}


def normalize_country(code):
    return COUNTRY_MAP.get(code, code)


# =========================
# LOGIN
# =========================
def login():
    r = requests.post(
        f"{BASE_URL}/login",
        json={"user": USER, "password": PASS},
        timeout=30
    )
    r.raise_for_status()

    token = r.json().get("Token") or r.json().get("token")
    if not token:
        raise Exception("Nova token missing")

    return token


# =========================
# STOCK
# =========================
def get_stock(token):
    r = requests.get(f"{BASE_URL}/stock/update/{token}", timeout=60)
    r.raise_for_status()

    data = r.json()

    return {
        str(p.get("Id")).strip(): int(p.get("Stock", 0))
        for p in data
        if p.get("Id") is not None
    }


# =========================
# ORDER NUMBER CLEAN
# =========================
def numeric_order_number(name):
    return re.sub(r"\D", "", str(name))[-15:]


# =========================
# MAIN FUNCTION
# =========================
def send_order_to_novaengel(order):

    try:
        token = login()
        stock = get_stock(token)

        logging.info(f"📦 Nova stock loaded: {len(stock)} items")

        lines = []

        for item in order.get("line_items", []):

            sku = (item.get("sku") or "").strip()
            title = item.get("title", "")

            logging.info(f"🔎 ITEM: {sku} | {title}")

            # ❌ skip non SKU
            if not sku:
                logging.warning("⚠️ Empty SKU skipped")
                continue

            # ❌ skip services / protection plans
            if item.get("product_id") is None:
                logging.warning(f"⚠️ Non-physical product skipped: {sku}")
                continue

            # ❌ unknown SKU
            if sku not in stock:
                logging.warning(f"❌ SKU not found in Nova: {sku}")
                continue

            # ❌ out of stock
            if stock[sku] <= 0:
                logging.warning(f"⚠️ Out of stock: {sku}")
                continue

            try:
                lines.append({
                    "productId": int(sku),
                    "units": int(item.get("quantity", 1))
                })
            except:
                logging.warning(f"⚠️ Invalid SKU format: {sku}")
                continue

        if not lines:
            logging.error("❌ No valid items for Nova")
            return {"status": "no_valid_items"}

        shipping = order.get("shipping_address") or order.get("billing_address")

        if not shipping:
            raise Exception("Missing shipping address")

        payload = [{
            "orderNumber": numeric_order_number(order.get("name", "")),
            "lines": lines,
            "name": shipping.get("first_name", ""),
            "secondName": shipping.get("last_name", ""),
            "street": shipping.get("address1", ""),
            "city": shipping.get("city", ""),
            "postalCode": shipping.get("zip", ""),
            "country": normalize_country(shipping.get("country_code", ""))
        }]

        logging.info(f"🚀 Sending to Nova: {payload}")

        r = requests.post(
            f"{BASE_URL}/orders/sendv2/{token}",
            json=payload,
            timeout=60
        )

        try:
            result = r.json()
        except:
            result = r.text

        logging.info(f"📩 Nova response: {result}")

        # ❌ force detection of Nova error
        if isinstance(result, list) and result and result[0].get("Message") == "KO":
            logging.error(f"❌ Nova rejected order: {result}")
            return {
                "status": "rejected",
                "nova_error": result
            }

        return {
            "status": "success",
            "nova_response": result
        }

    except Exception as e:
        logging.exception("❌ send_order_to_novaengel failed")
        return {
            "status": "error",
            "message": str(e)
        }
