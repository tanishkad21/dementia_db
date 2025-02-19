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

#  API Status Check
@app.route("/")
def home():
    return jsonify({"message": "Flask API is running on Render!"})

# Register User (Patients & Caregivers)
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
        token = create_access_token(identity={"id": user[0], "username": user[1], "role": user[3]})
        return jsonify({"token": token, "role": user[3]})
    return jsonify({"error": "Invalid username or password"}), 401

# Assign Caregiver to Patient
@app.route("/assign-caregiver", methods=["POST"])
@jwt_required()
def assign_caregiver():
    current_user = get_jwt_identity()
    
    # 🔥 Fix: Ensure current_user is extracted properly
    if isinstance(current_user, dict):
        patient_id = current_user.get("id")
    else:
        return jsonify({"error": "Invalid token format"}), 400

    if current_user.get("role") != "patient":
        return jsonify({"error": "Only patients can assign caregivers"}), 403

    data = request.get_json()
    caregiver_id = data.get("caregiver_id")
    can_edit_appointments = data.get("can_edit_appointments", False)
    can_edit_medications = data.get("can_edit_medications", False)
    can_view_daily_tasks = data.get("can_view_daily_tasks", True)

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "INSERT INTO caregiver_access (patient_id, caregiver_id, can_edit_appointments, can_edit_medications, can_view_daily_tasks) VALUES (%s, %s, %s, %s, %s)", 
            (patient_id, caregiver_id, can_edit_appointments, can_edit_medications, can_view_daily_tasks)
        )
        conn.commit()
        return jsonify({"message": "Caregiver assigned successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

# Retrieve Patient Data (Caregivers View Only)
@app.route("/patient-data/<int:patient_id>", methods=["GET"])
@jwt_required()
def get_patient_data(patient_id):
    current_user = get_jwt_identity()
    
    if isinstance(current_user, dict):
        caregiver_id = current_user.get("id")
    else:
        return jsonify({"error": "Invalid token format"}), 400

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cur.execute("SELECT * FROM caregiver_access WHERE caregiver_id = %s AND patient_id = %s", (caregiver_id, patient_id))
    access = cur.fetchone()
    
    if not access:
        return jsonify({"error": "Access denied"}), 403

    cur.execute("SELECT id, name, username FROM users WHERE id = %s", (patient_id,))
    patient = cur.fetchone()

    cur.execute("SELECT id, title, date, description FROM appointments WHERE user_id = %s", (patient_id,))
    appointments = cur.fetchall()

    cur.execute("SELECT id, name, dosage, time, duration FROM medications WHERE user_id = %s", (patient_id,))
    medications = cur.fetchall()

    cur.execute("SELECT id, name, location, time, frequency FROM daily_tasks WHERE user_id = %s", (patient_id,))
    daily_tasks = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "patient": {"id": patient[0], "name": patient[1], "username": patient[2]},
        "appointments": [{"id": appt[0], "title": appt[1], "date": appt[2], "description": appt[3]} for appt in appointments],
        "medications": [{"id": med[0], "name": med[1], "dosage": med[2], "time": med[3], "duration": med[4]} for med in medications],
        "daily_tasks": [{"id": task[0], "name": task[1], "location": task[2], "time": task[3], "frequency": task[4]} for task in daily_tasks]
    })

#  Start the Flask Application
if __name__ == "__main__":
    from gunicorn.app.base import BaseApplication

    class GunicornApp(BaseApplication):
        def load_config(self):
            self.cfg.set("bind", "0.0.0.0:10000")

        def load(self):
            return app

    GunicornApp().run()
