import time
from flask import Flask, request, jsonify, redirect, url_for, render_template, send_from_directory, make_response
import pyodbc
import hashlib
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies
)
import os
import logging

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your-secret-key'  # Required for signing tokens
app.config['JWT_TOKEN_LOCATION'] = ['cookies']  # Use cookies for token storage
app.config['JWT_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'  # Path for access token cookie
app.config['JWT_REFRESH_COOKIE_PATH'] = '/refresh'  # Path for refresh token cookie
app.config['JWT_COOKIE_CSRF_PROTECT'] = False  # Disable CSRF protection for simplicity
logging.basicConfig(level=logging.DEBUG)  # Set logging level to DEBUG
logger = logging.getLogger(__name__)  # Create a logger
logger.setLevel(logging.DEBUG)
logger.debug("Application started.")
CORS(app)
jwt = JWTManager(app)

@app.route('/static/<path:filename>')
@jwt_required()
def static_proxy(filename):
    current_user = get_jwt_identity()  # Get the user identity from the token
    logger.debug(f"Current user: {current_user}")
    return send_from_directory('static', filename)

@app.before_request
def log_request():
    logger.debug(f"Incoming request: {request.method} {request.url}")

@app.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)  # Use refresh=True for refresh tokens
def refresh():
    current_user = get_jwt_identity()  # Get the identity of the user
    new_access_token = create_access_token(identity=current_user)  # Create a new access token
    response = jsonify({'message': 'Token refreshed successfully'})
    set_access_cookies(response, new_access_token)  # Set the new access token in cookies
    return response, 200

def get_db_connection():
    conn = pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost;'
        'DATABASE=social-media-optimizer;'
        'UID=social-media-optimizer;'
        'PWD=social-media-optimizer'
    )
    return conn

@app.route('/login', methods=['GET', 'POST'])
@jwt_required(optional=True)  # Allow optional authentication
def login():
    if request.method == 'GET':
        # Check if the user is already authenticated
        current_user = get_jwt_identity()
        if current_user:
            next_url = request.args.get('next', '/')
            logger.debug(f"User {current_user} is already logged in, redirecting to {next_url}")
            return redirect(next_url)  # Redirect to the next page if authenticated

        # Render the login page if not authenticated
        next_url = request.args.get('next', '/')
        logger.debug(f"Rendering login page with next={next_url}")
        return render_template('login.html', next_url=next_url)

    elif request.method == 'POST':
        data = request.json
        username = data['username']
        password = data['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT PasswordHash FROM Users WHERE Username = ?', (username,))
        user = cursor.fetchone()

        if user:
            stored_password_hash = user[0]
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if password_hash == stored_password_hash:
                access_token = create_access_token(identity=username)
                refresh_token = create_refresh_token(identity=username)

                # Set the tokens in cookies
                response = jsonify({'message': 'Login successful'})
                set_access_cookies(response, access_token)
                set_refresh_cookies(response, refresh_token)
                return response, 200
            else:
                return jsonify({'error': 'Invalid username or password'}), 401
        else:
            return jsonify({'error': 'User not found'}), 404

@app.route('/logout', methods=['POST'])
def logout():
    response = jsonify({'message': 'Logout successful'})
    unset_jwt_cookies(response)  # Remove the tokens from cookies
    return response, 200

@app.route('/user-info')
@jwt_required()
def user_info():
    current_user = get_jwt_identity()
    # Fetch user details from the database using `current_user`
    return jsonify(username=current_user, email="email@example.com")  # Example data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/elements')
@jwt_required()
def elements():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('elements.html')

@app.route('/generic')
@jwt_required()
def generic():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('generic.html')


@app.route('/submit-form', methods=['POST'])
@jwt_required()
def submit_form():
    current_user = get_jwt_identity()
    data = request.json
    logger.debug(f"Form submitted by {current_user}: {data}")
    return jsonify({'message': 'Form submitted successfully!'}), 200

@app.route('/landing')
@jwt_required()
def landing():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('landing.html')

@app.route('/test')
def test():
    return render_template('test.html')

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data['username']
    password = data['password']
    email = data['email']

    # Hash the password for security
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Insert new user into the database
    try:
        cursor.execute('''
            INSERT INTO Users (Username, PasswordHash, Email)
            VALUES (?, ?, ?)
        ''', (username, password_hash, email))
        conn.commit()
        return jsonify({'message': 'User created successfully'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()




# Callback for invalid tokens
@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.debug(f"Invalid token error: {error}")
    return jsonify({"error": "Invalid token"}), 401

# Callback for expired tokens
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Expired token for user: {jwt_payload.get('sub')}")
    return jsonify({"error": "Token has expired"}), 401

# Callback for missing tokens
@jwt.unauthorized_loader
def missing_token_callback(error):
    logger.debug(f"Missing token error: {error}")
    return jsonify({"error": "Missing token"}), 401

# Callback for revoked tokens (if you use token revocation)
@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Revoked token for user: {jwt_payload.get('sub')}")
    return jsonify({"error": "Token has been revoked"}), 401


if __name__ == "__main__":
    app.run(debug=True, port=5000)
    render_template('index.html')