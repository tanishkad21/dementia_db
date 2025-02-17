from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Secure JWT for authentication
app.config["JWT_SECRET_KEY"] = "c780704a2cff91d016ecd5315b3b38cc465ddd862d7d497aa66517dc645b865566b2b0792d830dd47114f0caa9597d9c863d65282c699d54a1249ffa818994eb"  # Change this to a strong secret key
jwt = JWTManager(app)

# Connect to PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establish a database connection and return cursor + connection object"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    return conn, cur

# Register User (Securely Hash Passwords)
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data["username"]
    password = generate_password_hash(data["password"])  # Hash password before saving
    role = data["role"]

    conn, cur = get_db_connection()
    try:
        cur.execute("INSERT INTO users (username, password, role) VALUES (%s, %s, %s)", 
                    (username, password, role))
        conn.commit()
        return jsonify({"message": "User registered successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

# Login User (Verify Password Securely)
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data["username"]
    password = data["password"]

    conn, cur = get_db_connection()
    cur.execute("SELECT id, username, password, role FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and check_password_hash(user[2], password):  # Verify hashed password
        token = create_access_token(identity={"id": user[0], "username": user[1], "role": user[3]})
        return jsonify({"token": token})
    return jsonify({"message": "Invalid credentials"}), 401

# Protected Route: Get Appointments (Requires JWT Authentication)
@app.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    current_user = get_jwt_identity()  # Get user ID from JWT token

    conn, cur = get_db_connection()
    cur.execute("SELECT id, title, date, description FROM appointments WHERE user_id = %s", (current_user["id"],))
    appointments = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify([
        {"id": appt[0], "title": appt[1], "date": appt[2], "description": appt[3]} 
        for appt in appointments
    ])

# Add New Appointment (Requires JWT Authentication)
@app.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    current_user = get_jwt_identity()
    data = request.get_json()

    conn, cur = get_db_connection()
    try:
        cur.execute(
            "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
            (current_user["id"], data["title"], data["date"], data.get("description"))
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Appointment created!", "id": new_id})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    app.run(debug=True)
