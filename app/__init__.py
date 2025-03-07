from flask import Flask
from flask_cors import CORS
from app.config import Config
from app.extensions import mysql
from app.routes import register_routes

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Inisialisasi ekstensi
    mysql.init_app(app)
    
    # Setup CORS
    CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)
    
    # Register blueprint routes
    register_routes(app)

    return app
