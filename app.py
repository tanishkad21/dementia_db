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

#  Register User (Patients & Caregivers)
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

#  Login & Generate JWT Token
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
        token = create_access_token(identity=str(user[0]))  #  Ensure identity is a string
        return jsonify({"token": token, "role": user[3]})
    return jsonify({"error": "Invalid username or password"}), 401

#  Assign Caregiver to Patient
@app.route("/assign-caregiver", methods=["POST"])
@jwt_required()
def assign_caregiver():
    patient_id = int(get_jwt_identity())  # Convert back to int

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

#  Add Appointment
@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    user_id = int(get_jwt_identity())

    data = request.get_json()
    title, date, description = data.get("title"), data.get("date"), data.get("description")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, title, date, description)
        )
        conn.commit()
        return jsonify({"message": "Appointment added successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

#  Add Medication
@app.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    user_id = int(get_jwt_identity())

    data = request.get_json()
    name, dosage, time, duration = data.get("name"), data.get("dosage"), data.get("time"), data.get("duration")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "INSERT INTO medications (user_id, name, dosage, time, duration) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (user_id, name, dosage, time, duration)
        )
        conn.commit()
        return jsonify({"message": "Medication added successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

#  Add Daily Task
@app.route("/daily-tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    user_id = int(get_jwt_identity())

    data = request.get_json()
    name, location, time, frequency = data.get("name"), data.get("location"), data.get("time"), data.get("frequency")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (user_id, name, location, time, frequency)
        )
        conn.commit()
        return jsonify({"message": "Daily task added successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

#  Start the Flask Application
if __name__ == "__main__":
    from gunicorn.app.base import BaseApplication

    class GunicornApp(BaseApplication):
        def load_config(self):
            self.cfg.set("bind", "0.0.0.0:10000")

        def load(self):
            return app

    GunicornApp().run()
