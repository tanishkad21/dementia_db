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

# Send Caregiver Invite (Patient Only)
@app.route("/invite-caregiver", methods=["POST"])
@jwt_required()
def invite_caregiver():
    current_user = get_jwt_identity()
    if isinstance(current_user, str):
        return jsonify({"error": "Token format issue"}), 400

    if current_user["role"] != "patient":
        return jsonify({"error": "Only patients can invite caregivers"}), 403

    data = request.get_json()
    caregiver_username = data.get("caregiver_username")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cur.execute("SELECT id FROM users WHERE username = %s AND role = 'caregiver'", (caregiver_username,))
    caregiver = cur.fetchone()
    if not caregiver:
        return jsonify({"error": "Caregiver not found"}), 404

    caregiver_id = caregiver[0]

    try:
        cur.execute(
            "INSERT INTO caregiver_invites (patient_id, caregiver_id, status) VALUES (%s, %s, 'pending') ON CONFLICT DO NOTHING",
            (current_user["id"], caregiver_id)
        )
        conn.commit()
        return jsonify({"message": "Caregiver invite sent successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

# Get Pending Invites (Caregiver Only)
@app.route("/pending-invites", methods=["GET"])
@jwt_required()
def pending_invites():
    current_user = get_jwt_identity()
    if isinstance(current_user, str):
        return jsonify({"error": "Token format issue"}), 400

    if current_user["role"] != "caregiver":
        return jsonify({"error": "Only caregivers can view invites"}), 403

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    cur.execute(
        "SELECT patient_id FROM caregiver_invites WHERE caregiver_id = %s AND status = 'pending'",
        (current_user["id"],)
    )
    invites = cur.fetchall()
    
    cur.close()
    conn.close()

    return jsonify({"pending_invites": [invite[0] for invite in invites]})

# Accept Invite (Caregiver Only)
@app.route("/accept-invite", methods=["POST"])
@jwt_required()
def accept_invite():
    current_user = get_jwt_identity()
    if isinstance(current_user, str):
        return jsonify({"error": "Token format issue"}), 400

    if current_user["role"] != "caregiver":
        return jsonify({"error": "Only caregivers can accept invites"}), 403

    data = request.get_json()
    patient_id = data.get("patient_id")

    conn, cur = get_db_connection()
    if not conn:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "UPDATE caregiver_invites SET status = 'accepted' WHERE patient_id = %s AND caregiver_id = %s",
            (patient_id, current_user["id"])
        )
        cur.execute(
            "INSERT INTO caregiver_access (patient_id, caregiver_id, can_edit_appointments, can_edit_medications, can_view_daily_tasks) VALUES (%s, %s, FALSE, FALSE, TRUE) ON CONFLICT DO NOTHING",
            (patient_id, current_user["id"])
        )
        conn.commit()
        return jsonify({"message": "Caregiver invite accepted!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    app.run(debug=True)
