from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.db import execute_query

bp = Blueprint('appointments', __name__)

@bp.route("/appointments", methods=["GET"])
@jwt_required()
def get_appointments():
    user_id = get_jwt_identity()
    appts = execute_query("SELECT * FROM appointments WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(appts), 200

@bp.route("/appointments", methods=["POST"])
@jwt_required()
def add_appointment():
    data = request.get_json()
    user_id = get_jwt_identity()
    appt_id = execute_query(
        "INSERT INTO appointments (user_id, title, date, description) VALUES (%s, %s, %s, %s) RETURNING id",
        (user_id, data["title"], data["date"], data["description"]), return_id=True
    )
    return jsonify({"message": "Appointment added!", "id": appt_id}), 201

@bp.route("/appointments/<int:id>", methods=["PUT"])
@jwt_required()
def update_appointment(id):
    data = request.get_json()
    execute_query(
        "UPDATE appointments SET title=%s, date=%s, description=%s WHERE id=%s",
        (data["title"], data["date"], data["description"], id)
    )
    return jsonify({"message": "Appointment updated!"}), 200

@bp.route("/appointments/<int:id>", methods=["DELETE"])
@jwt_required()
def delete_appointment(id):
    execute_query("DELETE FROM appointments WHERE id = %s", (id,))
    return jsonify({"message": "Appointment deleted!"}), 200
