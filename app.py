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

# Logging all incoming requests for debugging
@app.before_request
def log_request_info():
    print(f"📡 API Request: {request.method} {request.url}")
    print(f"🔍 Headers: {request.headers}")
    print(f"📦 Body: {request.get_data().decode('utf-8')}")

# Database Connection Function
def get_db_connection():
    """ Establishes a database connection and returns the cursor. """
    try:
        print("🔗 Connecting to the database...")
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")  # Secure connection
        print("✅ Database connection successful!")
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
    """Registers a new user and stores their role in the database."""
    data = request.get_json()
    print(f"📡 Register API called: {request.method} {request.url}")
    print(f"🔍 Request Data: {data}")

    username, password, name, role = data.get("username"), data.get("password"), data.get("name", "Unnamed User"), data.get("role")

    if not username or not password or role not in ["patient", "caregiver"]:
        print("❌ Invalid registration data")
        return jsonify({"error": "Invalid registration data"}), 400

    hashed_password = generate_password_hash(password)
    
    print(f"📊 Executing SQL: INSERT INTO users (name, username, password, role) VALUES ('{name}', '{username}', <hashed_password>, '{role}')")
    user_id = execute_query(
        "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s) RETURNING id",
        (name, username, hashed_password, role),
        return_id=True
    )

    print(f"✅ User registered successfully! User ID: {user_id}") if user_id else print("❌ User registration failed!")

    return jsonify({"message": "User registered successfully!", "userId": user_id, "role": role}) if user_id else jsonify({"error": "Database error occurred"}), 500
# Login & Generate JWT Token
@app.route("/login", methods=["POST"])
def login():
    """Logs in a user and returns their role along with JWT token."""
    data = request.get_json()
    print(f"📡 Login API called: {request.method} {request.url}")
    print(f"🔍 Request Data: {data}")

    username, password = data.get("username"), data.get("password")
    if not username or not password:
        print("❌ Missing username or password")
        return jsonify({"error": "Username and password required"}), 400

    print(f"📊 Executing SQL: SELECT id, username, password, role FROM users WHERE username = '{username}'")
    user = execute_query("SELECT id, username, password, role FROM users WHERE username = %s", (username,), fetch_one=True)

    print(f"✅ Query Result: {user}") if user else print("❌ No user found!")

    if user and check_password_hash(user[2], password):
        token = create_access_token(identity=user[0])
        print(f"✅ Login successful for user ID: {user[0]}, Role: {user[3]}")
        return jsonify({"token": token, "userId": user[0], "role": user[3]})

    print("❌ Invalid login attempt")
    return jsonify({"error": "Invalid username or password"}), 401
# ✅ Add Medication Endpoint

@app.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    """Retrieve medications for the authenticated user."""
    user_id = get_jwt_identity()
    print(f"🔑 Extracted User ID: {user_id}")

    print(f"📊 Executing SQL: SELECT * FROM medications WHERE user_id = {user_id}")
    meds = execute_query(
        "SELECT id, name, dosage, time, duration, is_taken FROM medications WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )

    print(f"✅ Query Result: {meds}") if meds else print("❌ No medications found!")

    return jsonify([
        {"id": m[0], "name": m[1], "dosage": m[2], "time": m[3], "duration": m[4], "isTaken": bool(m[5])}
        for m in meds
    ])
@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    """Securely add a medication using JWT-based user identification."""
    user_id = get_jwt_identity()
    data = request.get_json()

    print(f"📡 Received Medication Request for User {user_id}: {data}")

    required_fields = ["name", "dosage", "time", "duration", "isTaken"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    inserted_id = execute_query(
        "INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"]),
        return_id=True
    )

    if not inserted_id:
        return jsonify({"error": "Failed to add medication"}), 500

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
        "isTaken": bool(new_medication[5])
    }), 201

@app.route("/medications/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_medication(id):
    """Delete an existing medication for the authenticated user."""
    user_id = get_jwt_identity()
    print(f"🔑 Extracted User ID: {user_id}")

    print(f"📊 Checking if medication ID {id} exists for user {user_id}")
    existing_med = execute_query(
        "SELECT id FROM medications WHERE id = %s AND user_id = %s",
        (id, user_id),
        fetch_one=True
    )

    if not existing_med:
        print(f"❌ Medication ID {id} not found for user {user_id}")
        return jsonify({"error": "Medication not found or access denied"}), 404

    print(f"📊 Deleting medication ID {id} for user {user_id}")
    success = execute_query("DELETE FROM medications WHERE id=%s AND user_id=%s", (id, user_id))

    print(f"✅ Medication deleted successfully!") if success else print("❌ Failed to delete medication!")
    return jsonify({"message": "Medication deleted successfully!"} if success else {"error": "Failed to delete medication"}), (200 if success else 500)

# Update Medication
@app.route("/medications/<int:id>", methods=["PUT"])
@jwt_required()
def update_medication(id):
    """Update an existing medication for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    required_fields = ["name", "dosage", "time", "duration", "isTaken"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Ensure medication exists and belongs to the user
    existing_med = execute_query(
        "SELECT id FROM medications WHERE id = %s AND user_id = %s",
        (id, user_id),
        fetch_one=True
    )

    if not existing_med:
        return jsonify({"error": "Medication not found or access denied"}), 404

    success = execute_query(
        "UPDATE medications SET name=%s, dosage=%s, time=%s, duration=%s, is_taken=%s WHERE id=%s AND user_id=%s",
        (data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"], id, user_id)
    )

    return jsonify({"message": "Medication updated successfully!"} if success else {"error": "Failed to update medication"}), (200 if success else 500)

@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    """Retrieve all appointments for the authenticated user."""
    user_id = get_jwt_identity()
    print(f"🔑 Extracted User ID: {user_id}")

    print(f"📊 Executing SQL: SELECT id, title, date, description FROM appointments WHERE user_id = {user_id}")
    appointments = execute_query(
        "SELECT id, title, date, description FROM appointments WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )

    print(f"✅ Query Result: {appointments}") if appointments else print("❌ No appointments found!")

    return jsonify([{ "id": a[0], "title": a[1], "date": a[2], "description": a[3] } for a in appointments])

# Update Appointment
@app.route("/appointments/<int:id>", methods=["PUT"])
@jwt_required()
def update_appointment(id):
    """Update an existing appointment for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()
    required_fields = ["title", "date", "description"]

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    success = execute_query(
        "UPDATE appointments SET title=%s, date=%s, description=%s WHERE id=%s AND user_id=%s",
        (data["title"], data["date"], data["description"], id, user_id)
    )

    return jsonify({"message": "Appointment updated successfully!"} if success else {"error": "Failed to update appointment"}), (200 if success else 500)

@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    """Create an appointment for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()

    print(f"📡 Received Appointment Request for User {user_id}: {data}")

    inserted_id = execute_query(
        "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, data["title"], data["date"], data["description"]),
        return_id=True
    )

    if not inserted_id:
        print("❌ Failed to add appointment!")
        return jsonify({"error": "Failed to add appointment"}), 500

    print(f"✅ Appointment added successfully! ID: {inserted_id}")
    return jsonify({"message": "Appointment added successfully!", "id": inserted_id}), 201

# Delete Appointment
@app.route("/appointments/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_appointment(id):
    """Delete an existing appointment for the authenticated user."""
    user_id = get_jwt_identity()

    success = execute_query("DELETE FROM appointments WHERE id=%s AND user_id=%s", (id, user_id))

    return jsonify({"message": "Appointment deleted successfully!"} if success else {"error": "Failed to delete appointment"}), (200 if success else 500)
# Update Daily Task
@app.route("/daily_tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    """Create a new daily task for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()

    print(f"📡 Received Daily Task Request for User {user_id}: {data}")

    inserted_id = execute_query(
        "INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["location"], data["time"], data["frequency"]),
        return_id=True
    )

    if not inserted_id:
        print("❌ Failed to add daily task!")
        return jsonify({"error": "Failed to add daily task"}), 500

    print(f"✅ Daily task added successfully! ID: {inserted_id}")
    return jsonify({"message": "Daily task added successfully!", "id": inserted_id}), 201

@app.route("/daily_tasks/<int:id>", methods=["PUT"])
@jwt_required()
def update_daily_task(id):
    """Update an existing daily task for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()
    required_fields = ["name", "location", "time", "frequency"]

    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    success = execute_query(
        "UPDATE daily_tasks SET name=%s, location=%s, time=%s, frequency=%s WHERE id=%s AND user_id=%s",
        (data["name"], data["location"], data["time"], data["frequency"], id, user_id)
    )

    return jsonify({"message": "Daily task updated successfully!"} if success else {"error": "Failed to update daily task"}), (200 if success else 500)

@app.route("/daily_tasks", methods=["GET"])
@jwt_required()
def get_daily_tasks():
    """Retrieve all daily tasks for the authenticated user."""
    user_id = get_jwt_identity()
    print(f"🔑 Extracted User ID: {user_id}")

    print(f"📊 Executing SQL: SELECT id, name, location, time, frequency FROM daily_tasks WHERE user_id = {user_id}")
    tasks = execute_query(
        "SELECT id, name, location, time, frequency FROM daily_tasks WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )

    print(f"✅ Query Result: {tasks}") if tasks else print("❌ No daily tasks found!")

    return jsonify([{ "id": t[0], "name": t[1], "location": t[2], "time": t[3], "frequency": t[4] } for t in tasks])

# Start the application using Gunicorn/Waitress for production
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure expects 8000
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
