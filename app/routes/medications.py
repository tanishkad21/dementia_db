from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.db import execute_query

bp = Blueprint('medications', __name__)

@bp.route("/medications", methods=["GET"])
@jwt_required()
def get_medications():
    user_id = get_jwt_identity()
    meds = execute_query("SELECT * FROM medications WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(meds), 200

@bp.route("/medications", methods=["POST"])
@jwt_required()
def add_medication():
    data = request.get_json()
    user_id = get_jwt_identity()
    med_id = execute_query(
        "INSERT INTO medications (user_id, name, dosage, time, duration, is_taken) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["dosage"], data["time"], data["duration"], data["is_taken"]), return_id=True
    )
    return jsonify({"message": "Medication added!", "id": med_id}), 201

@bp.route("/medications/<int:id>", methods=["PUT"])
@jwt_required()
def update_medication(id):
    data = request.get_json()
    execute_query(
        "UPDATE medications SET name=%s, dosage=%s, time=%s, duration=%s, is_taken=%s WHERE id=%s",
