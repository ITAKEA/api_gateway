from flask import Flask, jsonify, request
import requests
import sqlite3
import bcrypt
import os
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from dotenv import load_dotenv
from flasgger import swag_from
from swagger.config import init_swagger

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
DB_PATH = os.getenv('SQLITE_DB_PATH')
PORT = int(os.getenv('PORT', 5000))
GITHUB_MICROSERVICE_URL = os.getenv('GITHUB_MICROSERVICE_URL', 'http://github_microservice:5001')
jwt = JWTManager(app)

# Initialize Swagger
init_swagger(app)

# Database initialization
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database on startup
init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    return jsonify({
        "service": "API Gateway",
        "available_endpoints": [
            {
                "path": "/register",
                "method": "POST",
                "description": "Register a new user",
                "body": {
                    "username": "string",
                    "password": "string"
                },
                "TEST": "1234"
            },
            {
                "path": "/login",
                "method": "POST",
                "description": "Login to get JWT token",
                "body": {
                    "username": "string",
                    "password": "string"
                }
            },
            {
                "path": "/api/github/stats",
                "method": "GET",
                "description": "Get GitHub repository statistics",
                "authentication": "JWT required"
            }
        ]
    })

@app.route('/register', methods=['POST'])
@swag_from('swagger/register.yaml')
def register():
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing username or password"}), 400
    
    username = data['username']
    password = data['password']
    
    # Hash the password
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                 (username, hashed))
        conn.commit()
        return jsonify({"message": "User created successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
@swag_from('swagger/login.yaml')
def login():
    data = request.get_json()
    
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "Missing username or password"}), 400
    
    username = data['username']
    password = data['password']
    
    conn = get_db()
    c = conn.cursor()
    user = c.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
        access_token = create_access_token(identity=username)
        return jsonify({
            "message": "Login successful",
            "access_token": access_token
        })
    
    return jsonify({"error": "Invalid username or password"}), 401

@app.route('/api/github/stats', methods=['GET'])
@jwt_required()
@swag_from('swagger/github_stats.yaml')
def get_github_stats():
    try:
        current_user = get_jwt_identity()
        # Get the JWT token from the request header
        token = request.headers.get('Authorization')
        
        # Forward request to github_microservice with the token
        headers = {'Authorization': token}
        response = requests.get(f'{GITHUB_MICROSERVICE_URL}/github/stats', headers=headers)
        data = response.json()
        # Add user context to response
        data['requested_by'] = current_user
        return jsonify(data), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run()
