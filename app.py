from flask import Flask, request, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import psycopg2
import os
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

# Initialize Flask app
app = Flask(__name__)

# Enable CORS for cross-origin requests (Android & Web App Access)
CORS(app)

# Securely Load Environment Variables
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "default_secret")  # Ensure this is set in Azure!
jwt = JWTManager(app)

# Load Database URL from Azure Environment Variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ ERROR: DATABASE_URL is missing! Ensure it's set in Azure Configuration.")

# Logging all incoming requests for debugging
@app.before_request
def log_request_info():
    print(f"📡 API Request: {request.method} {request.url}")
    print(f"🔍 Headers: {request.headers}")
    print(f"📦 Body: {request.get_data().decode('utf-8')}")

# Database Connection Function
def get_db_connection():
    """ Establishes a database connection and returns the cursor. """
    try:
        print("🔗 Connecting to the database...")
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")  # Secure connection
        print("✅ Database connection successful!")
        cur = conn.cursor()
        return conn, cur
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return None, None

# Helper Function for Query Execution
def execute_query(query, params=(), fetch_one=False, fetch_all=False, return_id=False):
    """ General function to execute queries safely. """
    conn, cur = get_db_connection()
    if not conn:
        print("⚠️ Database connection failed during query execution.")
        return None

    try:
        print(f"📊 Executing SQL: {query} | Params: {params}")
        cur.execute(query, params)

        if return_id:
            result = cur.fetchone()[0]
            conn.commit()
            print(f"✅ Inserted record with ID: {result}")
            return result

        if fetch_one:
            result = cur.fetchone()
            print(f"✅ Fetch One Result: {result}")
            return result

        if fetch_all:
            result = cur.fetchall()
            print(f"✅ Fetch All Results: {result}")
            return result

        conn.commit()
        print("✅ Query executed successfully!")
        return True
    except psycopg2.Error as e:
        conn.rollback()
        print(f"⚠️ Database Query Error: {e}")
        return None
    finally:
        cur.close()
        conn.close()

# API Health Check
@app.route("/")
def home():
    return jsonify({"message": "Flask API is running successfully on Azure!"})

# Database Health Check
@app.route("/db-check")
def db_check():
    """Check if the database connection is successful."""
    conn, cur = get_db_connection()
    if conn:
        print("✅ Database connection verified.")
        cur.close()
        conn.close()
        return jsonify({"message": "Database connection is working!"}), 200
    print("❌ Database connection failed.")
    return jsonify({"error": "Database connection failed"}), 500

# Register User
@app.route("/register", methods=["POST"])
def register():
    """Registers a new user and stores their role in the database."""
    data = request.get_json()
    print(f"📡 Register API called: {request.method} {request.url}")
    print(f"🔍 Request Data: {data}")

    username, password, name, role = data.get("username"), data.get("password"), data.get("name", "Unnamed User"), data.get("role")

    if not username or not password or role not in ["patient", "caregiver"]:
        print("❌ Invalid registration data")
        return jsonify({"error": "Invalid registration data"}), 400

    hashed_password = generate_password_hash(password)
    
    print(f"📊 Storing user: {username} - Role: {role}")
    user_id = execute_query(
        "INSERT INTO users (name, username, password, role) VALUES (%s, %s, %s, %s) RETURNING id",
        (name, username, hashed_password, role),
        return_id=True
    )

    print(f"✅ User registered successfully! User ID: {user_id}") if user_id else print("❌ User registration failed!")

    return jsonify({"message": "User registered successfully!", "userId": user_id, "role": role}) if user_id else jsonify({"error": "Database error occurred"}), 500

# Login & Generate JWT Token
@app.route("/login", methods=["POST"])
def login():
    """Logs in a user and returns their role along with JWT token."""
    data = request.get_json()
    print("📡 Login API called with data:", data)

    # Ensure username and password are provided
    username, password = data.get("username"), data.get("password")
    if not username or not password:
        print("❌ Missing username or password")
        return jsonify({"error": "Username and password required"}), 400

    # Fetch user from database
    user = execute_query("SELECT id, username, password, role FROM users WHERE username = %s", (username,), fetch_one=True)

    print(f"🔍 Retrieved user from DB: {user}")

    if user and check_password_hash(user[2], password):
        user_id = str(user[0])  # Convert to string if needed for JWT
        role = user[3]  # Retrieve user role

        # Create JWT token with user ID
        token = create_access_token(identity=user_id)
        print(f"✅ Login successful. Token generated for User ID: {user_id}, Role: {role}")

        return jsonify({
            "token": token,
            "role": role,
            "user_id": user_id  # Keep the same field name as old version
        }), 200

    print("❌ Invalid username or password")
    return jsonify({"error": "Invalid username or password"}), 401

# Start the application using Gunicorn
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
