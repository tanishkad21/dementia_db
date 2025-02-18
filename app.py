from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "c780704a2cff91d016ecd5315b3b38cc465ddd862d7d497aa66517dc645b865566b2b0792d830dd47114f0caa9597d9c863d65282c699d54a1249ffa818994eb")
jwt = JWTManager(app)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Connect to PostgreSQL database on Neon.tech"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None, None

# ✅ Improved Register User with Debugging
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")
    name = data.get("name", "Unnamed User")  # ✅ Default to "Unnamed User" if missing
    role = data.get("role", "patient")  # Default role to 'patient'

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    hashed_password = generate_password_hash(password)

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute("INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)", 
                    (name, username, hashed_password, role))
        conn.commit()
        return jsonify({"message": "User registered successfully!", "username": username, "role": role})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 400
    finally:
        cur.close()
        conn.close()

# ✅ Improved Login with Better Error Messages
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    cur.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and check_password_hash(user[2], password):
        token = create_access_token(identity={"id": str(user[0]), "username": user[1], "role": user[3]})
        return jsonify({"token": token, "role": user[3]})
    return jsonify({"error": "Invalid username or password"}), 401

# ✅ Improved Get Appointments (Handles Unauthorized Users)
@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    current_user = get_jwt_identity()

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    if current_user["role"] == "patient":
        cur.execute("SELECT id, title, date, description FROM appointments WHERE user_id = %s", (current_user["id"],))
    else:
        cur.execute("""
            SELECT a.id, a.title, a.date, a.description 
            FROM appointments a
            JOIN caregiver_access ca ON a.user_id = ca.patient_id
            WHERE ca.caregiver_id = %s AND ca.can_edit_appointments = TRUE
        """, (current_user["id"],))

    appointments = cur.fetchall()
    cur.close()
    conn.close()

    if not appointments:
        return jsonify({"message": "No appointments found"}), 404

    return jsonify([{"id": appt[0], "title": appt[1], "date": appt[2], "description": appt[3]} for appt in appointments])

# ✅ Improved Add Appointment (Handles Caregiver Permissions)
@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    current_user = get_jwt_identity()
    data = request.get_json()

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    if current_user["role"] == "caregiver":
        cur.execute("SELECT can_edit_appointments FROM caregiver_access WHERE caregiver_id = %s AND patient_id = %s",
                    (current_user["id"], data["user_id"]))
        permission = cur.fetchone()

        if not permission or not permission[0]:  
            return jsonify({"error": "You do not have permission to add appointments"}), 403

    try:
        cur.execute(
            "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
            (data["user_id"], data["title"], data["date"], data.get("description"))
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Appointment created!", "id": new_id})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 400
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    app.run(debug=True)