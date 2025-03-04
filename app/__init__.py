from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from .db import init_db

app = Flask(__name__)
CORS(app)

# Securely load environment variables
app.config["JWT_SECRET_KEY"] = "your_secret_key_here"
jwt = JWTManager(app)

# Initialize database
init_db()

# Import routes
from app.routes import auth, medications, appointments, daily_tasks

app.register_blueprint(auth.bp)
app.register_blueprint(medications.bp)
app.register_blueprint(appointments.bp)
app.register_blueprint(daily_tasks.bp)
