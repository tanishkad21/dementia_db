import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

def load_config():
    return {
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", "default_secret"),
        "DATABASE_URL": os.getenv("DATABASE_URL")
    }
