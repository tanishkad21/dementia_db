from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Securely Load Environment Variables
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")
jwt = JWTManager(app)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("ERROR: DATABASE_URL is missing!")

# Database Connection Function
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None, None

# API Status Check
@app.route("/")
def home():
    return jsonify({"message": "Flask API is running on Render!"})

# Register User
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username, password, name, role = data.get("username"), data.get("password"), data.get("name", "Unnamed User"), data.get("role", "patient")

    if not username or not password or role not in ["patient", "caregiver"]:
        return jsonify({"error": "Invalid registration data"}), 400

    hashed_password = generate_password_hash(password)
    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute("INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)", 
                    (name, username, hashed_password, role))
        conn.commit()
        return jsonify({"message": "User registered successfully!"})
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "Username already exists. Please choose a different one."}), 400
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

# Login & Generate JWT Token
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username, password = data.get("username"), data.get("password")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cur.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and check_password_hash(user[2], password):
        token = create_access_token(identity=str(user[0]))  # Store ID as string
        return jsonify({"token": token, "role": user[3]})
    return jsonify({"error": "Invalid username or password"}), 401

# Helper functions
def fetch_results(query, params):
    conn, cur = get_db_connection()
    if not conn:
        return None
    cur.execute(query, params)
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results

def execute_query(query, params):
    conn, cur = get_db_connection()
    if not conn:
        return False
    try:
        cur.execute(query, params)
        conn.commit()
        return True
    except psycopg2.Error:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

# Medications Endpoints
@app.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    user_id = request.args.get("userId")
    meds = fetch_results("SELECT id, name, dosage, time, duration, is_taken FROM medications WHERE user_id = %s", (user_id,))
    return jsonify([{ "id": m[0], "name": m[1], "dosage": m[2], "time": m[3], "duration": m[4], "isTaken": m[5] } for m in meds])

@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    user_id = request.args.get("userId")
    data = request.get_json()
    success = execute_query("INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s)",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"]))
    return jsonify({"message": "Medication added successfully!"} if success else {"error": "Failed to add medication"})

@app.route("/medications/<int:id>", methods=["PUT"])
@jwt_required()
def update_medication(id):
    data = request.get_json()
    success = execute_query("UPDATE medications SET name=%s, dosage=%s, time=%s, duration=%s, is_taken=%s WHERE id=%s",
        (data["name"], data["dosage"], data["time"], data["duration"], data["isTaken"], id))
    return jsonify({"message": "Medication updated successfully!"} if success else {"error": "Failed to update medication"})

@app.route("/medications/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_medication(id):
    success = execute_query("DELETE FROM medications WHERE id=%s", (id,))
    return jsonify({"message": "Medication deleted successfully!"} if success else {"error": "Failed to delete medication"})

# Appointments Endpoints
@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    user_id = request.args.get("userId")
    appointments = fetch_results("SELECT id, title, date, description FROM appointments WHERE user_id = %s", (user_id,))
    return jsonify([{ "id": a[0], "title": a[1], "date": a[2], "description": a[3] } for a in appointments])

@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    user_id = request.args.get("userId")
    data = request.get_json()
    success = execute_query("INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s)",
        (user_id, data["title"], data["date"], data["description"]))
    return jsonify({"message": "Appointment added successfully!"} if success else {"error": "Failed to add appointment"})

@app.route("/appointments/<int:id>", methods=["PUT"])
@jwt_required()
def update_appointment(id):
    data = request.get_json()
    success = execute_query("UPDATE appointments SET title=%s, date=%s, description=%s WHERE id=%s",
        (data["title"], data["date"], data["description"], id))
    return jsonify({"message": "Appointment updated successfully!"} if success else {"error": "Failed to update appointment"})

@app.route("/appointments/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_appointment(id):
    success = execute_query("DELETE FROM appointments WHERE id=%s", (id,))
    return jsonify({"message": "Appointment deleted successfully!"} if success else {"error": "Failed to delete appointment"})

# Daily Tasks Endpoints
@app.route("/daily_tasks", methods=["GET"])
@jwt_required()
def get_daily_tasks():
    user_id = request.args.get("userId")
    tasks = fetch_results("SELECT id, name, location, time, frequency FROM daily_tasks WHERE user_id = %s", (user_id,))
    return jsonify([{ "id": t[0], "name": t[1], "location": t[2], "time": t[3], "frequency": t[4] } for t in tasks])

@app.route("/daily_tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    user_id = request.args.get("userId")
    data = request.get_json()
    success = execute_query("INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s)",
        (user_id, data["name"], data["location"], data["time"], data["frequency"]))
    return jsonify({"message": "Daily task added successfully!"} if success else {"error": "Failed to add daily task"})

if __name__ == "__main__":
    app.run(debug=True)
