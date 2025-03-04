from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.db import execute_query

bp = Blueprint('daily_tasks', __name__)

# ✅ GET: Retrieve all daily tasks for the authenticated user
@bp.route("/daily_tasks", methods=["GET"])
@jwt_required()
def get_daily_tasks():
    user_id = get_jwt_identity()
    tasks = execute_query("SELECT * FROM daily_tasks WHERE user_id = %s", (user_id,), fetch_all=True)
    return jsonify(tasks), 200 if tasks else jsonify({"message": "No tasks found"}), 404

# ✅ POST: Add a new daily task for the authenticated user
@bp.route("/daily_tasks", methods=["POST"])
@jwt_required()
def add_daily_task():
    data = request.get_json()
    user_id = get_jwt_identity()

    task_id = execute_query(
        "INSERT INTO daily_tasks (user_id, name, location, time, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, data["name"], data["location"], data["time"], data["frequency"]), return_id=True
    )

    return jsonify({"message": "Task added!", "id": task_id}), 201 if task_id else jsonify({"error": "Failed to add task"}), 500

# ✅ PUT: Update an existing daily task (only if user owns it)
@bp.route("/daily_tasks/<int:task_id>", methods=["PUT"])
@jwt_required()
def update_daily_task(task_id):
    data = request.get_json()
    user_id = get_jwt_identity()

    existing_task = execute_query("SELECT id FROM daily_tasks WHERE id = %s AND user_id = %s", (task_id, user_id), fetch_one=True)
    if not existing_task:
        return jsonify({"error": "Task not found or unauthorized"}), 403

    success = execute_query(
        "UPDATE daily_tasks SET name = %s, location = %s, time = %s, frequency = %s WHERE id = %s AND user_id = %s",
        (data["name"], data["location"], data["time"], data["frequency"], task_id, user_id)
    )

    return jsonify({"message": "Task updated successfully!"}), 200 if success else jsonify({"error": "Failed to update task"}), 500

# ✅ DELETE: Remove a daily task (only if user owns it)
@bp.route("/daily_tasks/<int:task_id>", methods=["DELETE"])
@jwt_required()
def delete_daily_task(task_id):
    user_id = get_jwt_identity()

    existing_task = execute_query("SELECT id FROM daily_tasks WHERE id = %s AND user_id = %s", (task_id, user_id), fetch_one=True)
    if not existing_task:
        return jsonify({"error": "Task not found or unauthorized"}), 403

    success = execute_query("DELETE FROM daily_tasks WHERE id = %s AND user_id = %s", (task_id, user_id))

    return jsonify({"message": "Task deleted successfully!"}), 200 if success else jsonify({"error": "Failed to delete task"}), 500
