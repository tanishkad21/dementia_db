from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token
from app.db import execute_query

bp = Blueprint('auth', __name__)

@bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username, password, name, role = data["username"], data["password"], data["name"], data["role"]

    if not username or not password or role not in ["patient", "caregiver"]:
        return jsonify({"error": "Invalid registration data"}), 400

    hashed_password = generate_password_hash(password)
    user_id = execute_query(
        "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s) RETURNING id",
        (name, username, hashed_password, role), return_id=True
    )

    return jsonify({"message": "User registered successfully!", "userId": user_id}) if user_id else jsonify({"error": "Database error"}), 500

@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username, password = data["username"], data["password"]

    user = execute_query("SELECT id, username, password, role FROM users WHERE username = %s", (username,), fetch_one=True)

    if user and check_password_hash(user[2], password):
        token = create_access_token(identity=str(user[0]))
        return jsonify({"token": token, "role": user[3], "user_id": user[0]}), 200

    return jsonify({"error": "Invalid username or password"}), 401
