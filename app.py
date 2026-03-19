import os
import logging
import hashlib

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from flask import Flask, request, jsonify, redirect, url_for, render_template, send_from_directory
from static.backend.extract_data import extract_data
from static.backend.load_to_db import load_to_db
from static.backend.enrich_comments import enrich_comments
from static.backend.db_connection import insert_new_user, fetch_user, fetch_distinct_comment_dimensions
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies
)

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your-secret-key'
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_SECURE'] = False
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
app.config['JWT_REFRESH_COOKIE_PATH'] = '/refresh'
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.debug("Application started.")

logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
CORS(app)
jwt = JWTManager(app)


@app.route('/static/<path:filename>')
@jwt_required()
def static_proxy(filename):
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return send_from_directory('static', filename)


@app.before_request
def log_request():
    logger.debug(f"Incoming request: {request.method} {request.url}")


@app.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user)
    response = jsonify({'message': 'Token refreshed successfully'})
    set_access_cookies(response, new_access_token)
    return response, 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        next_url = request.args.get('next', '/')

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
    return None


@app.route('/logout', methods=['POST'])
def logout():
    response = jsonify({'message': 'Logout successful'})
    unset_jwt_cookies(response)
    return response, 200


@app.route('/user-info')
@jwt_required()
def user_info():
    current_user = get_jwt_identity()
    return jsonify(username=current_user, email="email@example.com")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/elements')
@jwt_required()
def elements():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('elements.html')


@app.route('/extractor')
@jwt_required()
def extractor():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('extractor.html')


@app.route('/submit-form', methods=['POST'])
@jwt_required()
def submit_form():
    current_user = get_jwt_identity()
    data = request.json
    logger.debug(f"Form submitted by {current_user}: {data}")
    return jsonify({'message': 'Form submitted successfully!'}), 200


@app.route('/explorer')
@jwt_required()
def explorer():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    page_dimensions = {"page_names": [], "page_ids": []}
    page_loading_error = None
    try:
        page_dimensions = fetch_distinct_comment_dimensions()
    except Exception as exc:
        page_loading_error = str(exc)
        logger.exception("Failed to load distinct page dimensions for explorer.")

    return render_template(
        'explorer.html',
        current_user=current_user,
        page_names=page_dimensions["page_names"],
        page_ids=page_dimensions["page_ids"],
        page_loading_error=page_loading_error,
    )


@app.route('/advanced-analysis')
@jwt_required()
def advanced_analysis():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    insight_modules = [
        {
            "title": "Language Mix",
            "description": "Count comments by language to see audience composition for the selected dataset.",
            "outputs": "Bar chart, share cards, language filter presets",
        },
        {
            "title": "Sentiment by Language",
            "description": "Compare positive, neutral, and negative comments inside each detected language.",
            "outputs": "Stacked bars, ratio cards, raw comment sample panel",
        },
        {
            "title": "Sentiment by Post",
            "description": "Track how sentiment changes across post ids ordered by `PostTime`.",
            "outputs": "Post comparison chart, sortable post table, best/worst post highlights",
        },
        {
            "title": "Comment Length Analysis",
            "description": "Measure how comment length relates to language and sentiment.",
            "outputs": "Histogram, boxplots, outlier comments list",
        },
        {
            "title": "Solidarity Index",
            "description": "Reuse the current logic that compares comment sentiment with the first comment or post-description proxy.",
            "outputs": "Per-post solidarity score, per-language distribution, median/mean summary",
        },
        {
            "title": "Positivity Trend",
            "description": "Follow the share of positive comments across posts and smooth it as a trend over time.",
            "outputs": "Trend chart, language overlay, rolling positivity summary",
        },
    ]

    result_sections = [
        "Overview cards for comments, posts, latest load, and positivity share.",
        "Primary visualization area with switchable analysis modes.",
        "Drill-down table of posts or comments behind the selected chart.",
        "Representative positive, neutral, and negative comment samples.",
        "Export area for filtered comments and derived metrics.",
    ]

    return render_template(
        'advanced_analysis.html',
        current_user=current_user,
        insight_modules=insight_modules,
        result_sections=result_sections,
    )


@app.route('/faq')
@jwt_required()
def faq():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    schema_columns = [
        {"name": "CommentHash", "role": "Primary key", "description": "Stable SHA-256 identifier used for deduplication and upserts."},
        {"name": "PageName", "role": "Dimension", "description": "Display name of the Instagram page for grouping and filtering."},
        {"name": "PageID", "role": "Dimension", "description": "Stable page handle used as the main entity key in the UI."},
        {"name": "PostTime", "role": "Timeline anchor", "description": "Lets the interface build post-order and trend analysis over time."},
        {"name": "Comment", "role": "Core text", "description": "Raw input for language detection, sentiment, and qualitative review."},
        {"name": "CommentTime", "role": "Event time", "description": "Supports response windows, posting rhythm, and freshness filters."},
        {"name": "CommentLikes", "role": "Engagement signal", "description": "Weights notable comments and highlights audience resonance."},
        {"name": "LoadTime", "role": "Ingestion audit", "description": "Tracks when comments were loaded into the warehouse."},
        {"name": "Source", "role": "Lineage", "description": "Separates web-ingested data from future loaders or imports."},
        {"name": "UpdateTime", "role": "Change tracking", "description": "Indicates when an existing comment row was updated by MERGE."},
    ]

    pipeline_steps = [
        {
            "title": "1. Source Selection",
            "module": "Comments table",
            "description": "Select a page, period, source, and post window from the central table before any derived analysis runs.",
        },
        {
            "title": "2. Language Processing",
            "module": "process_data.py",
            "description": "Detect the dominant language of each comment and keep only language-consistent text for downstream analysis.",
        },
        {
            "title": "3. Sentiment Scoring",
            "module": "analyze_data.py",
            "description": "Run per-language sentiment models and label comments as positive, neutral, or negative.",
        },
        {
            "title": "4. Dataset Assembly",
            "module": "agregate_data.py",
            "description": "Assign post-level ids, keep per-comment ordering, and build the combined dataset for comparisons.",
        },
        {
            "title": "5. Insight Views",
            "module": "visualize_data.py",
            "description": "Render exploratory charts, solidarity analysis, positivity trends, and post-level drill-downs.",
        },
    ]

    purpose_sections = [
        {
            "title": "What the explorer page is for",
            "items": "Quick data exploration, filter selection, chart switching, and viewing the final analysis result.",
        },
        {
            "title": "What the FAQ page is for",
            "items": "Explain the source data, pipeline stages, available metrics, and how the workspace should evolve.",
        },
        {
            "title": "Why keep them separate",
            "items": "The analyst workspace stays focused, while the reference material remains available without cluttering the result screen.",
        },
    ]

    implementation_notes = [
        "Use the `Comments` table as the source of truth for filtering and retrieval.",
        "Move heavy processing into explicit backend stages or precomputed tables.",
        "Keep chart clicks connected to raw comments for validation.",
        "Use the FAQ page as product and technical reference for future contributors.",
    ]

    return render_template(
        'faq.html',
        current_user=current_user,
        schema_columns=schema_columns,
        pipeline_steps=pipeline_steps,
        purpose_sections=purpose_sections,
        implementation_notes=implementation_notes,
    )


@app.route('/test')
def test():
    return render_template('test.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    elif request.method == 'POST':
        data = request.json or request.form
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')

        if not username or not password or not email:
            return jsonify({'error': 'All fields are required'}), 400

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        insert_new_user(username, email, password_hash)
    return None


@app.route('/process-data', methods=['POST'])
def process_data_endpoint():
    try:
        params = request.json.get('params', {})
        target_page = params["param1"]
        number_of_posts = int(params["param2"])
        instagram_username = params["param3"]
        instagram_password = params["param4"]

        if not params:
            return jsonify({'error': 'No parameters provided.'}), 400


        # Step 1: Load data
        extract_data(instagram_username, instagram_password, target_page, number_of_posts)
        logger.debug("Starting load_to_db after extract_data")
        load_to_db(dry_run=False)
        logger.debug("load_to_db finished")

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
        logger.exception("process-data failed")
        return jsonify({'error': str(e)}), 500


@app.route('/enrich-comments', methods=['POST'])
@jwt_required()
def enrich_comments_endpoint():
    try:
        data = request.json or {}
        mode = data.get('mode')
        page_name = data.get('page_name')
        page_id = data.get('page_id')

        result = enrich_comments(mode=mode, page_name=page_name, page_id=page_id)
        return jsonify({'success': True, 'result': result}), 200
    except Exception as e:
        logger.exception("enrich-comments failed")
        return jsonify({'error': str(e)}), 500


@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.debug(f"Invalid token error: {error}")
    if request.headers.get("Accept") == "application/json":
        return jsonify({"error": "Invalid token", "action": "logout"}), 401
    else:
        next_url = request.path
        return redirect(url_for('login', next=next_url))


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Expired token for user: {jwt_payload.get('sub')}")
    if request.headers.get("Accept") == "application/json":
        return jsonify({"error": "Token has expired", "action": "refresh"}), 401
    else:
        next_url = request.path
        return redirect(url_for('login', next=next_url))


@jwt.unauthorized_loader
def missing_token_callback(error):
    logger.debug(f"Missing token error: {error}")
    if request.headers.get("Accept") == "application/json":
        return jsonify({"error": "Missing token", "action": "redirect_to_login"}), 401
    else:
        next_url = request.path
        return redirect(url_for('login', next=next_url))


@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    logger.debug(f"Revoked token for user: {jwt_payload.get('sub')}")
    if request.headers.get("Accept") == "application/json":
        return jsonify({"error": "Token has been revoked", "action": "logout"}), 401
    else:
        next_url = request.path
        return redirect(url_for('login', next=next_url))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
