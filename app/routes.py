from flask import Blueprint, request, jsonify, session
from app.extensions import mysql
from datetime import datetime
from functools import wraps
import json

routes = Blueprint('routes', __name__)

warehouse_mapping = {
    "Angsana": "IEL-KS-Angsana",
    "Bandung": "IEL-MU-BDG",
    "Kendari": "IEL-ST-KDI",
    "Jakarta": "JKT-JAV"
}

users = {"admin": "001"}
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"message": "Unauthorized. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function

def register_routes(app):
    app.register_blueprint(routes)

@routes.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username, password = data.get('username'), data.get('password')

    if username in users and password == "password":
        session['username'] = username
        return jsonify({"message": "Login successful!"}), 200
    return jsonify({"message": "Invalid credentials."}), 401

@routes.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"message": "Logged out successfully."}), 200

@routes.route('/api/check-session', methods=['GET'])
def check_session():
    if 'username' in session:
        return jsonify({"message": f"Logged in as {session['username']}"}), 200
    return jsonify({"message": "No active session, please log in."}), 401

@routes.route('/api/customers', methods=['GET'])
def search_customers():
    from app.models import Customer
    query = request.args.get('nama', '').strip()
    if not query:
        return jsonify([])
    
    try:
        results = Customer.get_customers(query)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500
    
@routes.route('/api/datapn', methods=['GET'])
def search_datapn():
    from app.models import PartNumber
    query = request.args.get('code', '').strip()
    if not query:
        return jsonify([])
    
    try:
        results = PartNumber.get_datapn(query)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500
    
@routes.route('/api/create_form', methods=['POST'])
def create_form():
    data = request.json
    items = data.get('items')
    username = session.get('username')

    if not items:
        return jsonify({"message": "At least one item is required."}), 400

    form_number = datetime.now().strftime("%d%m%Y") + f"-{users.get(username, '000')}-{int(datetime.timestamp(datetime.now()))}"

    try:
        conn = mysql.connection
        cursor = conn.cursor()
        submit_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            "INSERT INTO forms (form_number, username, submit_date) VALUES (%s, %s, %s)",
            (form_number, username, submit_date)
        )

        for idx, item in enumerate(items):
            check_result_item_id = f"{form_number}-{idx+1}"
            inventory_status = get_inventory_status(item["part_number"], item["quantity"])
            description = get_description(item["part_number"])

            result_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if any(
                "Available" in s or "Partial" in s for s in inventory_status.values()
            ) else None

            # Simpan ke form_items
            cursor.execute("""
                INSERT INTO form_items 
                (form_number, check_result_item_id, end_customer, order_point, part_number, description, quantity, result_date, inventory_status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                form_number, check_result_item_id, item["end_customer"], item["order_point"],
                item["part_number"], description, item["quantity"], result_date, json.dumps(inventory_status)
            ))

            # Simpan ke check_results
            cursor.execute("""
                INSERT INTO check_results 
                (form_number, check_result_item_id, submit_date, result_date, status, part_number, description, quantity, order_point, end_customer) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                form_number, check_result_item_id, submit_date, result_date, 
                "Pending" if result_date is None else "Completed", 
                item["part_number"], description, item["quantity"], 
                item["order_point"], item["end_customer"]
            ))

        conn.commit()
        cursor.close()
        return jsonify({"message": f"Form {form_number} created successfully!", "form_number": form_number}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"message": "Internal Server Error", "error": str(e)}), 500

def get_inventory_status(part_number, quantity):
    conn = mysql.connection
    cursor = conn.cursor()

    # Step 1: Cek PN di orderrequisition.datapn untuk mendapatkan description
    query = "SELECT `english_name` FROM orderrequisition.datapn WHERE `code` = %s"
    cursor.execute(query, (part_number,))
    result = cursor.fetchone()
    description = result['english_name'] if result else 'Unknown'

    # Step 2: Cek PN di realtimeinventory untuk mengecek status availability
    inventory_status = "Not Available"
    query = "SELECT `inventory_status`, `available_qty`, `warehouse_name` FROM realtimeinventory WHERE `code` = %s"
    cursor.execute(query, (part_number,))
    results = cursor.fetchall()

    warehouse_availability = {}

    for row in results:
        warehouse = row['warehouse_name'].strip()
        status = row['inventory_status']
        available_qty = row['available_qty']

        for key, value in warehouse_mapping.items():
            if warehouse == value:
                if status == "Available":
                    if available_qty >= quantity:
                        warehouse_availability[key] = "Available"
                    else:
                        warehouse_availability[key] = f"Partial (Stock = {available_qty})"
                elif status == "In-transit":
                    warehouse_availability[key] = "Checking Transfer Monitoring"

    # Step 3: Jika status "In-transit", cek transfermonitoring untuk ETA dan warehouse tujuan
    query = "SELECT `destination_warehouse`, `eta` FROM transfermonitoring WHERE `part_number` = %s"
    cursor.execute(query, (part_number,))
    transfer_result = cursor.fetchall()

    for row in transfer_result:
        warehouse = row['destination_warehouse'].strip()
        eta = row['eta']
        for key, value in warehouse_mapping.items():
            if warehouse == value:
                warehouse_availability[key] = f"In Transit (ETA = {eta})"

    # Step 4: Jika tidak ditemukan di transfermonitoring, cek di etachina
    if not transfer_result:
        query = "SELECT `eta` FROM etachina WHERE `part_number` = %s"
        cursor.execute(query, (part_number,))
        china_result = cursor.fetchone()
        if china_result:
            warehouse_availability["Jakarta"] = f"ETA from China to JKT = {china_result['eta']}"

    cursor.close()

    # Jika tidak ditemukan di semua tabel, status tetap "Not Available"
    if not warehouse_availability:
        warehouse_availability = {key: "Not Available" for key in warehouse_mapping}

    return {"status": warehouse_availability, "description": description}


def get_description(part_number):
    conn = mysql.connection
    cursor = conn.cursor()
    query = "SELECT `english_name` AS description FROM datapn WHERE `code` = %s LIMIT 1"
    cursor.execute(query, (part_number,))
    result = cursor.fetchone()
    cursor.close()
    return result['description'] if result else 'Unknown'
@routes.route('/api/check_result', methods=['GET'])
def get_check_results():
    try:
        conn = mysql.connection
        cursor = conn.cursor()
        query = """
        SELECT 
            c.form_number, c.check_result_item_id, c.submit_date, c.result_date, c.status,
            c.part_number, c.description, c.quantity, c.order_point, c.end_customer,
            f.inventory_status,
            GROUP_CONCAT(CONCAT(a.alternative_part_number, ' - ', a.alternative_description) SEPARATOR ', ') AS alternative_parts
        FROM check_results c
        LEFT JOIN form_items f ON c.check_result_item_id = f.check_result_item_id
        LEFT JOIN alternative_part_numbers a ON c.check_result_item_id = a.check_result_item_id
        GROUP BY c.check_result_item_id;
        """
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        response = jsonify(results)
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:3000")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500

# Get check results by form number
@routes.route('/api/check_result/<form_number>', methods=['GET'])
def get_check_result_by_form_number(form_number):
    try:
        conn = mysql.connection
        cursor = conn.cursor()
        query = """
        SELECT 
            c.form_number, c.check_result_item_id, c.submit_date, c.result_date, c.status,
            c.part_number, c.description, c.quantity, c.order_point, c.end_customer,
            f.inventory_status,
            GROUP_CONCAT(CONCAT(a.alternative_part_number, ' - ', a.alternative_description) SEPARATOR ', ') AS alternative_parts
        FROM check_results c
        LEFT JOIN form_items f ON c.check_result_item_id = f.check_result_item_id
        LEFT JOIN alternative_part_numbers a ON c.check_result_item_id = a.check_result_item_id
        WHERE c.form_number = %s
        GROUP BY c.check_result_item_id;
        """
        cursor.execute(query, (form_number,))
        results = cursor.fetchall()
        cursor.close()
        
        if not results:
            return jsonify({"message": "Form not found."}), 404
        
        response = jsonify(results)
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:3000")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Credentials", "true")
        return response

    except Exception as e:
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500
    
@routes.route('/api/additional_documents', methods=['POST'])
def create_additional_documents():
    try:
        data = request.get_json()
        print("Data Received:", data)  # Debugging

        if not data or 'items' not in data:
            return jsonify({'error': 'Invalid request, missing items'}), 400

        items = data['items']
        if not isinstance(items, list):
            return jsonify({'error': 'Items must be a list'}), 400

        conn = mysql.connection  # Flask-MySQL connection
        cursor = conn.cursor()

        for item in items:
            print("Inserting item:", item)  # Debugging sebelum eksekusi query
            cursor.execute("""
                INSERT INTO additional_documents (part_number, description, vin_number, engine_number, unit_type, quantity)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (item["part_number"], item["description"], item["vin_number"], 
                  item["engine_number"], item["unit_type"], item["quantity"]))

        conn.commit()
        cursor.close()  # Hanya menutup cursor, bukan koneksi utama

        return jsonify({'message': 'Data inserted successfully', 'data': items}), 201
    except Exception as e:
        print("Error inserting data:", str(e))  # Debugging error
        return jsonify({'error': str(e)}), 500

@routes.route('/api/additional_documents_result', methods=['GET'])
def get_additional_documents_result():
    try:
        conn = mysql.connection
        cursor = conn.cursor()

        # Ambil parameter pencarian dari query string
        search_query = request.args.get('search', '')

        # Buat query SQL dengan pencarian (gunakan wildcard % untuk LIKE)
        if search_query:
            cursor.execute("""
                SELECT * FROM additional_documents 
                WHERE part_number LIKE %s OR description LIKE %s OR 
                    vin_number LIKE %s OR engine_number LIKE %s OR 
                    unit_type LIKE %s
            """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", 
                f"%{search_query}%", f"%{search_query}%"))
        else:
            cursor.execute("SELECT * FROM additional_documents")

        documents = cursor.fetchall()
        column_names = [desc[0] for desc in cursor.description]
        documents_list = [dict(zip(column_names, row)) for row in documents]

        cursor.close()
        conn.close()

        print("Returning data:", documents_list)  # Debugging
        response = jsonify(documents_list)
        response.headers.add("Access-Control-Allow-Origin", "http://localhost:3000")
        response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Credentials", "true")

        return response, 200
    except Exception as e:
        print("Error fetching data:", str(e))  # Debugging error
        return jsonify({'error': str(e)}), 500

