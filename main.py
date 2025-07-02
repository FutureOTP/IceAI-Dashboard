import os
from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
import secrets
import logging

from config import Config
from database import init_db
from routes import register_routes

# Load environment variables
load_dotenv()

def create_app():
    """Application factory pattern"""
    app = Flask(__name__, template_folder="templates", static_folder="static")
    
    # Configuration
    app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
    CORS(app)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Validate configuration
    Config.validate()
    
    # Initialize database
    init_db()
    
    # Register routes
    register_routes(app)
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)