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


# ✅ Add Medication Endpoint

@app.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    """Retrieve medications for the authenticated user."""
    user_id = get_jwt_identity()  # Extract user ID from the JWT token

    # Retrieve medications only for the logged-in user
    meds = execute_query(
        "SELECT id, name, dosage, time, duration, is_taken FROM medications WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )

    if meds is None:  # Handle possible query failure
        return jsonify({"error": "Failed to fetch medications"}), 500

    return jsonify([
        {
            "id": m[0],
            "name": m[1],
            "dosage": m[2],
            "time": m[3],
            "duration": m[4],
            "isTaken": bool(m[5])  # Ensure correct boolean format
        }
        for m in meds
    ]), 200

@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    """Securely add a medication using JWT-based user identification."""
    user_id = get_jwt_identity()  # Extract user ID from JWT token
    data = request.get_json()  # Get JSON request body

    print(f"📡 Received Medication Request for User {user_id}: {data}")

    # Ensure all required fields are provided
    required_fields = ["name", "dosage", "time", "duration", "isTaken"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    # Insert medication with correct user_id
    inserted_id = execute_query(
        "INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"]),
        return_id=True
    )

    if not inserted_id:
        return jsonify({"error": "Failed to add medication"}), 500

    # Retrieve newly inserted medication
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
        "isTaken": bool(new_medication[5])  # Ensure boolean format
    }), 201

# Get Appointments for User
@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    """Retrieve all appointments for the authenticated user."""
    user_id = get_jwt_identity()
    appointments = execute_query(
        "SELECT id, title, date, description FROM appointments WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )
    return jsonify([{ "id": a[0], "title": a[1], "date": a[2], "description": a[3] } for a in appointments])

# Add a New Appointment
@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    """Create an appointment for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()

    inserted_id = execute_query(
        "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, data["title"], data["date"], data["description"]),
        return_id=True
    )

    if not inserted_id:
        return jsonify({"error": "Failed to add appointment"}), 500

    return jsonify({"message": "Appointment added successfully!", "id": inserted_id}), 201

# Get Daily Tasks for User
@app.route("/daily_tasks", methods=["GET"])
@jwt_required()
def get_daily_tasks():
    """Retrieve all daily tasks for the authenticated user."""
    user_id = get_jwt_identity()
    tasks = execute_query(
        "SELECT id, name, location, time, frequency FROM daily_tasks WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )
    return jsonify([{ "id": t[0], "name": t[1], "location": t[2], "time": t[3], "frequency": t[4] } for t in tasks])

# Add a New Daily Task
@app.route("/daily_tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    """Create a new daily task for the authenticated user."""
    user_id = get_jwt_identity()
    data = request.get_json()

    inserted_id = execute_query(
        "INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["location"], data["time"], data["frequency"]),
        return_id=True
    )

    if not inserted_id:
        return jsonify({"error": "Failed to add daily task"}), 500

    return jsonify({"message": "Daily task added successfully!", "id": inserted_id}), 201
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

# Delete Medication
@app.route("/medications/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_medication(id):
    """Delete an existing medication for the authenticated user."""
    user_id = get_jwt_identity()

    # Ensure medication exists and belongs to the user before deleting
    existing_med = execute_query(
        "SELECT id FROM medications WHERE id = %s AND user_id = %s",
        (id, user_id),
        fetch_one=True
    )

    if not existing_med:
        return jsonify({"error": "Medication not found or access denied"}), 404

    success = execute_query(
        "DELETE FROM medications WHERE id=%s AND user_id=%s", (id, user_id)
    )

    return jsonify({"message": "Medication deleted successfully!"} if success else {"error": "Failed to delete medication"}), (200 if success else 500)

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


# Delete Appointment
@app.route("/appointments/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_appointment(id):
    """Delete an existing appointment for the authenticated user."""
    user_id = get_jwt_identity()

    success = execute_query("DELETE FROM appointments WHERE id=%s AND user_id=%s", (id, user_id))

    return jsonify({"message": "Appointment deleted successfully!"} if success else {"error": "Failed to delete appointment"}), (200 if success else 500)
# Update Daily Task
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


# Delete Daily Task
@app.route("/daily_tasks/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_daily_task(id):
    """Delete an existing daily task for the authenticated user."""
    user_id = get_jwt_identity()

    success = execute_query("DELETE FROM daily_tasks WHERE id=%s AND user_id=%s", (id, user_id))

    return jsonify({"message": "Daily task deleted successfully!"} if success else {"error": "Failed to delete daily task"}), (200 if success else 500)


# Start the application using Gunicorn/Waitress for production
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Azure expects 8000
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
