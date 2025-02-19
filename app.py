from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "c780704a2cff91d016ecd5315b3b38cc465ddd862d7d497aa66517dc645b865566b2b0792d830dd47114f0caa9597d9c863d65282c699d54a1249ffa818994eb")
jwt = JWTManager(app)

def get_db_connection():
    """Connect to PostgreSQL database on Neon.tech"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f" X Database Connection Error: {e}")
        return None, None

# Register User (Patient or Caregiver)
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username, password, name, role = data.get("username"), data.get("password"), data.get("name", "Unnamed User"), data.get("role", "patient")

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    hashed_password = generate_password_hash(password)
    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute("INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s)", (name, username, hashed_password, role))
        conn.commit()
        return jsonify({"message": "User registered successfully!", "username": username, "role": role})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 400
    finally:
        cur.close()
        conn.close()

# Assign a Caregiver to a Patient
@app.route("/assign-caregiver", methods=["POST"])
@jwt_required()
def assign_caregiver():
    current_user = get_jwt_identity()
    if current_user["role"] != "patient":
        return jsonify({"error": "Only patients can assign caregivers"}), 403

    data = request.get_json()
    caregiver_id = data.get("caregiver_id")

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    try:
        cur.execute(
            "INSERT INTO caregiver_access (patient_id, caregiver_id) VALUES (%s, %s)", 
            (current_user["id"], caregiver_id)
        )
        conn.commit()
        return jsonify({"message": "Caregiver assigned successfully!"})
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 400
    finally:
        cur.close()
        conn.close()

# Get Patient Data (Caregivers Can View)
@app.route("/patient-data/<int:patient_id>", methods=["GET"])
@jwt_required()
def get_patient_data(patient_id):
    current_user = get_jwt_identity()

    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    # Check if caregiver has access
    cur.execute("SELECT * FROM caregiver_access WHERE caregiver_id = %s AND patient_id = %s", (current_user["id"], patient_id))
    access = cur.fetchone()
    
    if not access:
        return jsonify({"error": "You do not have permission to view this patient's data"}), 403

    # Fetch patient details
    cur.execute("SELECT id, name, username FROM users WHERE id = %s", (patient_id,))
    patient = cur.fetchone()

    # Fetch patient’s appointments, medications, and tasks
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

# Generate Daily Report for Caregivers
@app.route("/generate-report/<int:patient_id>", methods=["POST"])
@jwt_required()
def generate_report(patient_id):
    current_user = get_jwt_identity()
    
    conn, cur = get_db_connection()
    if conn is None or cur is None:
        return jsonify({"error": "Database connection failed"}), 500

    # Check if caregiver has access
    cur.execute("SELECT * FROM caregiver_access WHERE caregiver_id = %s AND patient_id = %s", (current_user["id"], patient_id))
    access = cur.fetchone()
    
    if not access:
        return jsonify({"error": "You do not have permission to generate this report"}), 403

    # Fetch completed tasks, taken medications, and appointments
    cur.execute("SELECT COUNT(*) FROM daily_tasks WHERE user_id = %s", (patient_id,))
    tasks_completed = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM medications WHERE user_id = %s AND is_taken = TRUE", (patient_id,))
    medications_taken = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM appointments WHERE user_id = %s", (patient_id,))
    appointments_attended = cur.fetchone()[0]

    cur.execute(
        "INSERT INTO daily_reports (patient_id, caregiver_id, completed_tasks, medications_taken, appointments_summary) VALUES (%s, %s, %s, %s, %s)",
        (patient_id, current_user["id"], tasks_completed, medications_taken, appointments_attended)
    )
    conn.commit()
    return jsonify({"message": "Daily report generated!"})

if __name__ == "__main__":
    app.run(debug=True)
