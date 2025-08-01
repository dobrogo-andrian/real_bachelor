from flask import Flask, request, jsonify, redirect, url_for, render_template, send_from_directory
from static.backend.load_data import load_data
from static.backend.db_connection import insert_new_user, fetch_user
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        next_url = request.args.get('next', '/')

        # Prevent redirect loops by resetting `next` if it points to `/login`
        if next_url == '/login':
            next_url = '/'

        logger.debug(f"Rendering login page with next={next_url}")
        return render_template('login.html', next_url=next_url)

    elif request.method == 'POST':
        data = request.json
        username = data['username']
        password = data['password']

        user = fetch_user(username)

        if user:
            stored_password_hash = user[0]
            password_hash = hashlib.sha256(password.encode()).hexdigest()
            if password_hash == stored_password_hash:
                access_token = create_access_token(identity=username)
                refresh_token = create_refresh_token(identity=username)

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


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        # Render the signup page
        return render_template('signup.html')  # Ensure you have a `signup.html` template

    elif request.method == 'POST':
        data = request.json or request.form
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')

        if not username or not password or not email:
            return jsonify({'error': 'All fields are required'}), 400

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        insert_new_user(username, email, password_hash)


@app.route('/process-data', methods=['POST'])
def process_data_endpoint():
    try:
        # Get parameters from the request (JSON payload)
        params = request.json.get('params', {})
        target_page = params["param1"]
        number_of_posts = int(params["param2"])
        instagram_username = params["param3"]
        instagram_password = params["param4"]

        # Validate input
        if not params:
            return jsonify({'error': 'No parameters provided.'}), 400

        # Execute the sequence of functions
        # Step 1: Load data
        data = load_data(instagram_username, instagram_password, target_page, number_of_posts)

        # # Step 2: Analyze data
        # analyzed_data = analyze_data(data)
        # # Step 3: Aggregate data
        # aggregated_data = aggregate_data(analyzed_data)
        # # Step 4: Process data
        # final_result = process_data(aggregated_data)

        # Return the final result to the frontend
        return jsonify(
            {'success': True, 'result': (target_page, number_of_posts, instagram_username, instagram_password)}), 200
    except Exception as e:
        # Handle unexpected errors
        return jsonify({'error': str(e)}), 500


@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.debug(f"Invalid token error: {error}")
    # Check if the request is an API call (e.g., AJAX or Fetch)
    if request.headers.get("Accept") == "application/json":
        # Return a JSON response for API requests
        return jsonify({"error": "Invalid token", "action": "logout"}), 401
    else:
        # Redirect to the login page for non-API requests (e.g., browser page loads)
        next_url = request.path  # Preserve the original path for redirection
        return redirect(url_for('login', next=next_url))


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Expired token for user: {jwt_payload.get('sub')}")
    # Check if the request is an API call (e.g., AJAX or Fetch)
    if request.headers.get("Accept") == "application/json":
        # Return a JSON response for API requests
        return jsonify({"error": "Token has expired", "action": "refresh"}), 401  # Suggest refresh
    else:
        # Redirect to the login page for non-API requests (e.g., browser page loads)
        next_url = request.path  # Preserve the original path for redirection
        return redirect(url_for('login', next=next_url))


# Callback for missing tokens
@jwt.unauthorized_loader
def missing_token_callback(error):
    logger.debug(f"Missing token error: {error}")
    # Check if the request is an API call (e.g., AJAX or Fetch)
    if request.headers.get("Accept") == "application/json":
        # Return a JSON response for API requests
        return jsonify({"error": "Missing token", "action": "redirect_to_login"}), 401  # Suggest login
    else:
        # Redirect to the login page for non-API requests (e.g., browser page loads)
        next_url = request.path  # Preserve the original path for redirection
        return redirect(url_for('login', next=next_url))


# Callback for revoked tokens
@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Revoked token for user: {jwt_payload.get('sub')}")
    if request.headers.get("Accept") == "application/json":
        # Return a JSON response for API requests
        return jsonify({"error": "Token has been revoked", "action": "logout"}), 401  # Suggest logout
    else:
        # Redirect to the login page for non-API requests (e.g., browser page loads)
        next_url = request.path  # Preserve the original path for redirection
        return redirect(url_for('login', next=next_url))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
