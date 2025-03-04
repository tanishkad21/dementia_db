from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for cross-origin requests (Android & Web App Access)
CORS(app)

# Securely Load Environment Variables
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "default_secret")  # Ensure this is set in Azure!
jwt = JWTManager(app)

# Load Database URL from Azure Environment Variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERROR: DATABASE_URL is missing! Ensure it's set in Azure Configuration.")

# Database Connection Function
def get_db_connection():
    """ Establishes a database connection and returns the cursor. """
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")  # Secure connection
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None, None

# Helper Function for Query Execution
def execute_query(query, params, fetch_one=False, fetch_all=False, return_id=False):
    """ General function to execute queries safely. """
    conn, cur = get_db_connection()
    if not conn:
        print("⚠️ Database connection failed during query execution.")
        return None

    try:
        cur.execute(query, params)

        if return_id:
            result = cur.fetchone()[0]
            conn.commit()
            return result

        if fetch_one:
            result = cur.fetchone()
            cur.close()
            conn.close()
            return result

        if fetch_all:
            result = cur.fetchall()
            cur.close()
            conn.close()
            return result

        conn.commit()
        return True
    except psycopg2.Error as e:
        conn.rollback()
        print(f"⚠️ Database Query Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# API Health Check
@app.route("/")
def home():
    return jsonify({"message": "Flask API is running successfully on Azure!"})

# Register User
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    print("📡 Register API called with data:", data)
    
    username, password, name, role = data.get("username"), data.get("password"), data.get("name", "Unnamed User"), data.get("role", "patient")

    if not username or not password or role not in ["patient", "caregiver"]:
        return jsonify({"error": "Invalid registration data"}), 400

    hashed_password = generate_password_hash(password)
    success = execute_query(
        "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)",
        (name, username, hashed_password, role)
    )

    return jsonify({"message": "User registered successfully!"} if success else {"error": "Database error occurred"}), (201 if success else 500)

# Login & Generate JWT Token
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    print("📡 Login API called with data:", data)

    username, password = data.get("username"), data.get("password")
    user = execute_query("SELECT id, username, password, role FROM users WHERE username = %s", (username,), fetch_one=True)

    if user and check_password_hash(user[2], password):
        token = create_access_token(identity=str(user[0]))
        return jsonify({"token": token, "role": user[3]})

    return jsonify({"error": "Invalid username or password"}), 401

# ✅ Updated Medications Endpoint with Debugging & Returning Inserted Data
@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    user_id = request.args.get("userId")
    data = request.get_json()

    print("📡 Received API request:", data)

    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    inserted_id = execute_query(
        "INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"]),
        return_id=True
    )

    if not inserted_id:
        return jsonify({"error": "Failed to add medication"}), 500

    # Retrieve inserted medication
    new_medication = execute_query(
        "SELECT id, name, dosage, time, duration, is_taken FROM medications WHERE id = %s",
        (inserted_id,),
        fetch_one=True
    )

    if not new_medication:
        return jsonify({"error": "Failed to retrieve medication"}), 500

    return jsonify({
        "id": new_medication[0],
        "name": new_medication[1],
        "dosage": new_medication[2],
        "time": new_medication[3],
        "duration": new_medication[4],
        "isTaken": new_medication[5]
    })

# Medications Endpoints
@app.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    user_id = request.args.get("userId")
    meds = execute_query(
        "SELECT id, name, dosage, time, duration, is_taken FROM medications WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )
    return jsonify([{ "id": m[0], "name": m[1], "dosage": m[2], "time": m[3], "duration": m[4], "isTaken": m[5] } for m in meds])

@app.route("/medications/<int:id>", methods=["PUT"])
@jwt_required()
def update_medication(id):
    data = request.get_json()
    success = execute_query(
        "UPDATE medications SET name=%s, dosage=%s, time=%s, duration=%s, is_taken=%s WHERE id=%s",
        (data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"], id)
    )
    return jsonify({"message": "Medication updated successfully!"} if success else {"error": "Failed to update medication"})

@app.route("/medications/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_medication(id):
    success = execute_query("DELETE FROM medications WHERE id=%s", (id,))
    return jsonify({"message": "Medication deleted successfully!"} if success else {"error": "Failed to delete medication"})

# ✅ Appointments and Daily Tasks remain unchanged but use the new helper function
@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    user_id = request.args.get("userId")
    data = request.get_json()
    success = execute_query(
        "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s)",
        (user_id, data["title"], data["date"], data["description"])
    )
    return jsonify({"message": "Appointment added successfully!"} if success else {"error": "Failed to add appointment"})

# Start the application using Gunicorn/Waitress for production
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure expects 8000
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
