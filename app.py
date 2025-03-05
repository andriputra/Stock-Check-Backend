from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS, cross_origin
from datetime import datetime
import uuid
from functools import wraps
import mysql.connector

from flask_mysqldb import MySQL
from flask_login import login_required

# # (TAMBAHAN API)
# from kingdee_client import KingdeeClient
# import logging

# # (TAMBAHAN API)
# logging.basicConfig(
#     level=logging.DEBUG,  # Set the logging level
#     format='%(levelname)s:(%(filename)s:%(lineno)d) - %(message)s'
# )

app = Flask(__name__)

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'orderrequisition'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'\

app.secret_key = 'your_secret_key'
app.config['SESSION_COOKIE_SECURE'] = True  # Ensures cookies are only sent over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevents JavaScript access to cookies
app.config['SESSION_COOKIE_SAMESITE'] = 'None'  # For cross-site requests

CORS(app, origins=["http://localhost:3000"], supports_credentials=True)  # Enable CORS to allow frontend requests

# Simulated Databases
users = {
    "admin": "001"  # User identifier for 'admin' is '001'
}


forms = []  # To store form submissions

# Mapping Warehouse Names
warehouse_mapping = {
    "Angsana": "IEL-KS-Angsana",
    "Sofifi": "IEL-MU-SFI",
    "Kendari": "IEL-ST-KDI",
    "Jakarta": "JKT-JAV"
}

# Middleware: Protect Routes with Login
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"message": "Unauthorized. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function

# Helper function to generate a unique form number
def generate_form_number(username):
    today = datetime.now().strftime("%d%m%Y")
    user_id = users.get(username, "000")  # Default to '000' if user ID not found

    # Count existing forms for this user today
    user_forms_today = [
        f for f in forms if f["form_number"].startswith(f"{today}-{user_id}")
    ]
    form_count = len(user_forms_today) + 1
    form_number = f"{today}-{user_id}-{form_count:03d}"  # 3-digit sequential number
    return form_number

# Fungsi untuk mendapatkan inventory status dari database
def get_inventory_status(part_number):
    # Koneksi ke database
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="password",
        database="orderrequisition"
    )
    cursor = conn.cursor(dictionary=True)

    # Query untuk mendapatkan status inventory berdasarkan part_number dan warehouse
    query = """
        SELECT 
            `Warehouse Name` AS warehouse, 
            `Inventory Status` AS status
        FROM 
            realtimeinventory
        WHERE 
            `Material Code` = %s
    """
    cursor.execute(query, (part_number,))
    results = cursor.fetchall()

    # Menutup koneksi
    cursor.close()
    conn.close()

    # Default status jika tidak ditemukan di warehouse tertentu
    inventory_status = {
        "Jakarta": "Not Available",
        "Sofifi": "Not Available",
        "Kendari": "Not Available",
        "Angsana": "Not Available"
    }

    for row in results:
        db_warehouse = row['warehouse'].strip()  # Menghapus spasi di awal/akhir
        status = row['status']

        # Cek apakah warehouse dari database cocok dengan mapping
        for key, value in warehouse_mapping.items():
            if db_warehouse == value:
                inventory_status[key] = status

    return inventory_status

def get_description(part_number):
    # Koneksi ke database
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="password",
        database="orderrequisition"
    )
    cursor = conn.cursor(dictionary=True)

    # Query untuk mengambil deskripsi dari tabel datapn
    query = """
        SELECT 
            `English Name` AS description
        FROM 
            datapn
        WHERE 
            `code` = %s
        LIMIT 1
    """
    cursor.execute(query, (part_number,))
    result = cursor.fetchone()

    # Menutup koneksi
    cursor.close()
    conn.close()

    # Mengembalikan deskripsi atau 'Unknown' jika tidak ditemukan
    return result['description'] if result else 'Unknown'

# Serve Static Files (Frontend)
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../frontend', path)

# Login Route
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if username in users and password == "password":  # Static password for simplicity
        session['username'] = username
        response = jsonify({"message": "Login successful!"})
        response.status_code = 200
        return response
    return jsonify({"message": "Invalid credentials."}), 401

# Logout Route
@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('username', None)
    return jsonify({"message": "Logged out successfully."}), 200

# Create Form Route
# @app.route('/api/create_form', methods=['POST'])
# @login_required
# def create_form():
#     data = request.json
#     items = data.get('items')
#     username = session.get('username')

#     # Validate items
#     if not items or len(items) == 0:
#         return jsonify({"message": "At least one item is required."}), 400

#     # Generate a single Form Number
#     form_number = generate_form_number(username)
#     # # (TAMBAHAN API)
#     # client = KingdeeClient("./conf.ini")

#     # Process each item
#     for idx, item in enumerate(items):
#         # # (TAMBAHAN API) update di sini
#         # client.check_stock_availability(input={
#         #     'create_org_id': 102,
#         #     'id': "",
#         #     'number': item["part_number"]   # sebelumnya 'number': ""   
#         # })

#         check_result_item_id = f"{form_number}-{idx+1}"
        
#         # Ambil inventory status dari database
#         inventory_status = get_inventory_status(item["part_number"])
        
#         # Ambil description dari database `datapn`
#         description = get_description(item["part_number"])

#          # Cek apakah inventory status sudah muncul (Available atau Not Available)
#         has_result = any(
#             status in ["Available", "Not Available"] for status in inventory_status.values()
#         )
        
#         # Jika hasil inventory sudah muncul (baik Available maupun Not Available), set result_date
#         result_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if has_result else None

#         form = {
#             "form_number": form_number,
#             "check_result_item_id": check_result_item_id,
#             "submit_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "end_customer": item["end_customer"],
#             "order_point": item["order_point"],
#             "part_number": item["part_number"],
#             "description": description,
#             "quantity": item["quantity"],
#             "result_date": result_date,
#             "inventory_status": inventory_status
#         }
#         forms.append(form)

#     return jsonify({"message": f"Form {form_number} created successfully with {len(items)} items!", "form_number": form_number}), 201
@app.route('/api/create_form', methods=['POST'])
@login_required
def create_form():
    data = request.json
    items = data.get('items')
    username = session.get('username')

    if not items or len(items) == 0:
        return jsonify({"message": "At least one item is required."}), 400

    # Generate Form Number
    form_number = generate_form_number(username)

    try:
        cur = mysql.connection.cursor()

        # Insert ke tabel `forms`
        submit_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT INTO forms (form_number, username, submit_date) VALUES (%s, %s, %s)",
                    (form_number, username, submit_date))
        mysql.connection.commit()

        # Insert items ke `form_items`
        for idx, item in enumerate(items):
            check_result_item_id = f"{form_number}-{idx+1}"

            # Ambil inventory status dan description dari database
            inventory_status = get_inventory_status(item["part_number"])
            description = get_description(item["part_number"])

            has_result = any(status in ["Available", "Not Available"] for status in inventory_status.values())
            result_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if has_result else None

            cur.execute("""
                INSERT INTO form_items 
                (form_number, check_result_item_id, end_customer, order_point, part_number, description, quantity, result_date, inventory_status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (form_number, check_result_item_id, item["end_customer"], item["order_point"],
                  item["part_number"], description, item["quantity"], result_date, str(inventory_status)))

        mysql.connection.commit()
        cur.close()

        return jsonify({"message": f"Form {form_number} created successfully with {len(items)} items!", "form_number": form_number}), 201

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"message": "Internal Server Error", "error": str(e)}), 500

# Check Results Route
@app.route('/api/check_result', methods=['GET'])
@login_required
def check_result():
    result = []
    for form in forms:
        result.append({
            "form_number": form["form_number"],
            "check_result_item_id": form["check_result_item_id"],
            "submit_date": form["submit_date"],
            "result_date": form["result_date"],
            "status": "Done" if form["result_date"] else "Pending",
            "end_customer": form["end_customer"],
            "part_number": form["part_number"],
            "description": form["description"],
            "quantity": form["quantity"],
            "order_point": form["order_point"],
            "inventory_status": form["inventory_status"]
        })
    return jsonify(result), 200

# Get Form Details Route
@app.route('/form_details/<form_number>', methods=['GET'])
@login_required
def form_details(form_number):
    # Get all items for the given form_number
    items = [f for f in forms if f["form_number"] == form_number]
    if not items:
        return jsonify({"message": "Form not found"}), 404

    return jsonify({
        "form_number": form_number,
        "items": [
            {
                "check_result_item_id": item["check_result_item_id"],
                "end_customer": item["end_customer"],
                "order_point": item["order_point"],
                "part_number": item["part_number"],
                "description": item["description"],
                "quantity": item["quantity"],
                "result_date": item["result_date"],
                "inventory_status": item["inventory_status"]
            }
            for item in items
        ]
    }), 200

@app.route('/test', methods=['POST'])
def test_api():
    return jsonify({"message": "API is working!"}), 200
    
@app.route('/api/check-session', methods=['GET'])
def check_session():
    if 'username' in session:
        return jsonify({"message": f"Logged in as {session['username']}"})
    else:
        return jsonify({"message": "No active session, please log in."}), 401

# @app.after_request
# def apply_caching(request):

#     request.headers["Access-Control-Allow-Origin"] = "*"
#     request.headers["Access-Control-Allow-Headers"] = "Authentication, Content-Type, Content-Length, Content-Encoding, Content-Language, Content-Location"
#     # request.headers["Access-Control-Allow-Headers"] = "Content-Type, Content-Length, Content-Encoding, Content-Language, Content-Location, Content-Range, Content-Security-Policy, Content-Security-Policy-Report-Only"
#     request.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, UPDATE, DELETE"
#     request.headers["Access-Control-Max-Age"] = "86400"
#     return request

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


if __name__ == '__main__':
    # app.run(debug=True)
    app.run(host="127.0.0.1", port=5000, debug=True)
