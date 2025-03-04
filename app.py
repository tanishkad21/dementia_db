from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from .db import execute_query  # Make sure this is available


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
    
    # Only log body if it's a small JSON request (prevents huge logs)
    if request.content_type == "application/json":
        try:
            print(f"📦 Body: {request.get_json()}")
        except Exception:
            print("⚠️ Unable to parse JSON body.")

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
def execute_query(query, params=(), fetch_one=False, fetch_all=False, return_id=False):
    """ General function to execute queries safely. """
    conn, cur = get_db_connection()
    if not conn or not cur:
        print("⚠️ Database connection failed during query execution.")
        return None

    try:
        print(f"📊 Executing SQL: {query} | Params: {params}")
        cur.execute(query, params)

        if return_id:
            result = cur.fetchone()[0]
            conn.commit()
            print(f"✅ Inserted record with ID: {result}")
            return result

        if fetch_one:
            result = cur.fetchone()
            print(f"✅ Fetch One Result: {result}")
            return result

        if fetch_all:
            result = cur.fetchall()
            print(f"✅ Fetch All Results: {result}")
            return result

        conn.commit()
        print("✅ Query executed successfully!")
        return True
    except psycopg2.Error as e:
        conn.rollback()
        print(f"⚠️ Database Query Error: {e}")
        return None
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# API Health Check
@app.route("/")
def home():
    return jsonify({"message": "Flask API is running successfully on Azure!"})


# Database Health Check
@app.route("/db-check")
def db_check():
    """Check if the database connection is successful."""
    conn, cur = get_db_connection()
    
    if conn and cur:  # Ensure both are valid
        print("✅ Database connection verified.")
        cur.close()
        conn.close()
        return jsonify({"message": "Database connection is working!"}), 200
    
    print("❌ Database connection failed.")  # Now this will always print properly
    return jsonify({"error": "Database connection failed"}), 500
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
    
    print(f"📊 Storing user: {username} - Role: {role}")
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
    print("📡 Login API called with data:", data)

    # Ensure username and password are provided
    username, password = data.get("username"), data.get("password")
    if not username or not password:
        print("❌ Missing username or password")
        return jsonify({"error": "Username and password required"}), 400

    # Fetch user from database
    user = execute_query("SELECT id, username, password, role FROM users WHERE username = %s", (username,), fetch_one=True)

    print(f"🔍 Retrieved user from DB: {user}")

    if user and check_password_hash(user[2], password):
        user_id = str(user[0])  # Convert to string if needed for JWT
        role = user[3]  # Retrieve user role

        # Create JWT token with user ID
        token = create_access_token(identity=user_id)
        print(f"✅ Login successful. Token generated for User ID: {user_id}, Role: {role}")

        return jsonify({
            "token": token,
            "role": role,
            "user_id": user_id  # Keep the same field name as old version
        }), 200

    print("❌ Invalid username or password")
    return jsonify({"error": "Invalid username or password"}), 401

#### ---------------------- 🏥 MEDICATIONS ---------------------- ####

@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    """ Add a new medication for the authenticated user """
    data = request.get_json()
    user_id = get_jwt_identity()

    medication_id = execute_query(
        "INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"]),
        return_id=True
    )

    return jsonify({"message": "Medication added!", "medication_id": medication_id}), 201 if medication_id else 500


@app.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    """ Get all medications for the authenticated user """
    user_id = get_jwt_identity()
    medications = execute_query("SELECT * FROM medications WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(medications), 200 if medications else jsonify([]), 200


@app.route("/medications/<int:id>", methods=["PUT"])
@jwt_required()
def update_medication(id):
    """ Update a medication by ID """
    data = request.get_json()
    user_id = get_jwt_identity()

    success = execute_query(
        "UPDATE medications SET name=%s, dosage=%s, time=%s, duration=%s, is_taken=%s WHERE id=%s AND user_id=%s",
        (data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"], id, user_id)
    )

    return jsonify({"message": "Medication updated!" if success else "Failed to update"}), 200 if success else 500


@app.route("/medications/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_medication(id):
    """ Delete a medication by ID """
    user_id = get_jwt_identity()
    success = execute_query("DELETE FROM medications WHERE id=%s AND user_id=%s", (id, user_id))
    return jsonify({"message": "Medication deleted!" if success else "Failed to delete"}), 200 if success else 500


#### ---------------------- 📅 APPOINTMENTS ---------------------- ####

@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    """ Add a new appointment """
    data = request.get_json()
    user_id = get_jwt_identity()

    appointment_id = execute_query(
        "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, data["title"], data["date"], data["description"]),
        return_id=True
    )

    return jsonify({"message": "Appointment added!", "appointment_id": appointment_id}), 201 if appointment_id else 500


@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    """ Get all appointments for the user """
    user_id = get_jwt_identity()
    appointments = execute_query("SELECT * FROM appointments WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(appointments), 200 if appointments else jsonify([]), 200


@app.route("/appointments/<int:id>", methods=["PUT"])
@jwt_required()
def update_appointment(id):
    """ Update an appointment """
    data = request.get_json()
    user_id = get_jwt_identity()

    success = execute_query(
        "UPDATE appointments SET title=%s, date=%s, description=%s WHERE id=%s AND user_id=%s",
        (data["title"], data["date"], data["description"], id, user_id)
    )

    return jsonify({"message": "Appointment updated!" if success else "Failed to update"}), 200 if success else 500


@app.route("/appointments/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_appointment(id):
    """ Delete an appointment """
    user_id = get_jwt_identity()
    success = execute_query("DELETE FROM appointments WHERE id=%s AND user_id=%s", (id, user_id))
    return jsonify({"message": "Appointment deleted!" if success else "Failed to delete"}), 200 if success else 500


#### ---------------------- ✅ DAILY TASKS ---------------------- ####

@app.route("/daily_tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    """ Add a new daily task """
    data = request.get_json()
    user_id = get_jwt_identity()

    task_id = execute_query(
        "INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["location"], data["time"], data["frequency"]),
        return_id=True
    )

    return jsonify({"message": "Task added!", "task_id": task_id}), 201 if task_id else 500


@app.route("/daily_tasks", methods=["GET"])
@jwt_required()
def get_daily_tasks():
    """ Get all daily tasks """
    user_id = get_jwt_identity()
    tasks = execute_query("SELECT * FROM daily_tasks WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(tasks), 200 if tasks else jsonify([]), 200


@app.route("/daily_tasks/<int:id>", methods=["PUT"])
@jwt_required()
def update_daily_task(id):
    """ Update a daily task """
    data = request.get_json()
    user_id = get_jwt_identity()

    success = execute_query(
        "UPDATE daily_tasks SET name=%s, location=%s, time=%s, frequency=%s WHERE id=%s AND user_id=%s",
        (data["name"], data["location"], data["time"], data["frequency"], id, user_id)
    )

    return jsonify({"message": "Task updated!" if success else "Failed to update"}), 200 if success else 500


@app.route("/daily_tasks/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_daily_task(id):
    """ Delete a daily task """
    user_id = get_jwt_identity()
    success = execute_query("DELETE FROM daily_tasks WHERE id=%s AND user_id=%s", (id, user_id))
    return jsonify({"message": "Task deleted!" if success else "Failed to delete"}), 200 if success else 500


# Start the application using Gunicornif __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
    except Exception as e:
        print(f"🔥 Flask failed to start, running Gunicorn: {e}")
        subprocess.run(["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"])