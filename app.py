from flask import Flask, jsonify, request
import logging
import os
from orders import send_order_to_novaengel

app = Flask(_name_)
logging.basicConfig(level=logging.INFO)

@app.route("/")
def home():
    return "Nova Engel Connector – READY ✅"

@app.route("/shopify/order-created", methods=["POST"])
def shopify_order_created():
    order = request.get_json()
    logging.info(f"Commande reçue: {order.get('name')}")
    result = send_order_to_novaengel(order)
    return jsonify(result), 200

if _name_ == "_main_":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))