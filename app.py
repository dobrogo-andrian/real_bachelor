import os
import logging
import hashlib

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from flask import Flask, request, jsonify, redirect, url_for, render_template, send_from_directory, make_response
from static.backend.extract_data import extract_data
from static.backend.load_to_db import load_to_db
from static.backend.enrich_comments import enrich_comments
from static.backend.explorer_analysis import build_page_analysis, build_analysis_from_rows
from static.backend.db_connection import (
    insert_new_user,
    fetch_user,
    fetch_user_instagram_credentials,
    fetch_distinct_comment_dimensions,
    fetch_existing_post_hrefs,
    fetch_advanced_comment_dimensions,
    fetch_enriched_comment_preview,
    fetch_enriched_comment_rows,
)
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies
)

app = Flask(__name__, static_folder=None)
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
        response = make_response(render_template('login.html', next_url=next_url))
        unset_jwt_cookies(response)
        return response

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
    advanced_dimensions = {
        "page_names": [],
        "page_ids": [],
        "sources": [],
        "languages": [],
        "sentiments": [],
        "ranges": {},
    }
    page_loading_error = None
    try:
        advanced_dimensions = fetch_advanced_comment_dimensions()
    except Exception as exc:
        page_loading_error = str(exc)
        logger.exception("Failed to load advanced analysis dimensions.")

    return render_template(
        'advanced_analysis.html',
        current_user=current_user,
        advanced_dimensions=advanced_dimensions,
        page_loading_error=page_loading_error,
    )


@app.route('/api/advanced-analysis/preview', methods=['POST'])
@jwt_required()
def advanced_analysis_preview():
    payload = request.get_json(silent=True) or {}
    logger.debug("Advanced analysis preview payload: %s", payload)
    try:
        preview = fetch_enriched_comment_preview(payload, limit=100)
        analysis_rows = fetch_enriched_comment_rows(payload)
        analysis = build_analysis_from_rows(
            analysis_rows,
            selection_type="advanced_filters",
            selection_value="filtered_subset",
            filters=payload,
        )
        preview["analysis"] = analysis
        return jsonify(preview), 200
    except Exception as exc:
        logger.exception("Failed to fetch advanced analysis preview.")
        return jsonify({"error": str(exc)}), 500


@app.route('/api/advanced-analysis/analyze', methods=['POST'])
@jwt_required()
def advanced_analysis_analyze():
    payload = request.get_json(silent=True) or {}
    logger.debug("Advanced analysis chart payload: %s", payload)
    try:
        analysis_rows = fetch_enriched_comment_rows(payload)
        analysis = build_analysis_from_rows(
            analysis_rows,
            selection_type="advanced_filters",
            selection_value="filtered_subset",
            filters=payload,
        )
        return jsonify({"analysis": analysis}), 200
    except Exception as exc:
        logger.exception("Failed to build advanced analysis charts.")
        return jsonify({"error": str(exc)}), 500


@app.route('/faq')
@jwt_required()
def faq():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    page_sections = [
        {
            "title": "Home",
            "route": "/",
            "access": "Public",
            "summary": "Landing page for the whole workspace. It introduces the product, links to every main page, and reflects whether the visitor is already authenticated.",
            "details": [
                "Shows the current workspace scope: extractor, explorer, advanced analysis, FAQ, signup, and login.",
                "Detects an existing session from the browser and replaces login prompts with a logged-in indicator.",
                "Acts as the safest re-entry point when a user is deciding which workflow page to open next.",
            ],
        },
        {
            "title": "Login",
            "route": "/login",
            "access": "Public",
            "summary": "Authentication entry page for application users. Opening this page also resets any existing JWT cookie session before showing the form.",
            "details": [
                "Accepts the application username and password stored in the `Users` table.",
                "Uses the `next` query parameter to return the user to the protected page they originally requested.",
                "Always clears the current session on page load so the login form starts from a clean authentication state.",
            ],
        },
        {
            "title": "Sign Up",
            "route": "/signup",
            "access": "Public",
            "summary": "Account creation page for new operators. It creates the application account and stores encrypted Instagram credentials for later extraction jobs.",
            "details": [
                "Collects username, email, application password, Instagram login, and Instagram password.",
                "Hashes the application password before storage and protects Instagram credentials with reversible encryption.",
                "Prepares the user record so later workflows can use saved Instagram credentials without storing them as plaintext.",
            ],
        },
        {
            "title": "Extractor",
            "route": "/extractor",
            "access": "Authenticated",
            "summary": "Data ingestion page. It is responsible for starting the Instagram extraction flow and loading new comments into the database.",
            "details": [
                "Accepts a target page, number of posts, and Instagram credentials for the extraction session.",
                "Calls the backend extraction script and then loads the result into SQL Server through `load_to_db`.",
                "Should be used first whenever fresh comments are needed before any analytical work can begin.",
            ],
        },
        {
            "title": "Explorer",
            "route": "/explorer",
            "access": "Authenticated",
            "summary": "Primary analysis page for page-level exploration. It lets the user select a page, run analysis, and inspect result summaries built from the warehouse.",
            "details": [
                "Loads distinct page names and page ids from the `Comments` table.",
                "Focuses on guided exploration rather than arbitrary row-level filtering.",
                "Works best when the user already knows which Instagram page or page id they want to review.",
            ],
        },
        {
            "title": "Advanced Analysis",
            "route": "/advanced-analysis",
            "access": "Authenticated",
            "summary": "Detailed filter workspace for enriched comments. It goes beyond Explorer by allowing direct row preview and more granular segment construction.",
            "details": [
                "Supports combined filtering by page name, page id, source, language, sentiment, likes, time windows, and text search.",
                "Returns both row previews and aggregated analysis derived from the filtered subset.",
                "Is the right page when the user needs precise slices of the dataset instead of a broader page-level overview.",
            ],
        },
        {
            "title": "FAQ",
            "route": "/faq",
            "access": "Authenticated",
            "summary": "Reference page for the entire application. It documents what every page does, how the data model is structured, and how the processing pipeline is organized.",
            "details": [
                "Keeps product and technical reference material separate from the live analysis workflows.",
                "Documents the shared source tables, enrichment stages, and intended responsibilities of each page.",
                "Also contains the contact section for questions, handoff notes, or future maintenance work.",
            ],
        },
        {
            "title": "Elements",
            "route": "/elements",
            "access": "Authenticated",
            "summary": "Template support page inherited from the base theme. It is not part of the main analysis workflow but remains available as a design and component reference.",
            "details": [
                "Useful when comparing existing UI components from the HTML template.",
                "Can be removed later if the project no longer needs the theme reference page.",
                "Should not be presented as a core analytical step for end users.",
            ],
        },
        {
            "title": "Test",
            "route": "/test",
            "access": "Public",
            "summary": "Utility page for local experiments and temporary checks. It is not a documented end-user workflow page.",
            "details": [
                "Can be used for isolated frontend or backend verification during development.",
                "Should stay clearly separated from the production-facing navigation.",
                "May be removed or repurposed once its temporary development value is gone.",
            ],
        },
    ]

    faq_reference = {
        "schema_columns": [
            {"name": "CommentHash", "role": "Primary key", "description": "Stable SHA-256 identifier used for deduplication and upserts."},
            {"name": "PageName", "role": "Dimension", "description": "Display name of the Instagram page for grouping and filtering."},
            {"name": "PageID", "role": "Dimension", "description": "Stable page handle used as the main entity key in the UI."},
            {"name": "PostTime", "role": "Timeline anchor", "description": "Lets the interface build post-order and trend analysis over time."},
            {"name": "Comment", "role": "Core text", "description": "Raw input for language detection, sentiment, and qualitative review."},
            {"name": "CommentTime", "role": "Event time", "description": "Supports response windows, posting rhythm, and freshness filters."},
            {"name": "CommentLikes", "role": "Engagement signal", "description": "Weights notable comments and highlights audience resonance."},
            {"name": "LoadTime", "role": "Ingestion audit", "description": "Tracks when comments were loaded into the warehouse."},
            {"name": "Source", "role": "Lineage", "description": "Separates web-ingested data from future loaders or imports."},
        ],
        "pipeline_steps": [
            {
                "title": "1. Source Selection",
                "module": "Comments table",
                "description": "choose a page, period, source, and post window from the central table before any derived analysis runs.",
            },
            {
                "title": "2. Language Processing",
                "module": "enrich_comments.py",
                "description": "Normalize comment text, detect the dominant language, and prepare consistent text for downstream analysis.",
            },
            {
                "title": "3. Sentiment Scoring",
                "module": "enrich_comments.py",
                "description": "Run the language-specific sentiment models and classify comments as positive, neutral, or negative.",
            },
            {
                "title": "4. Dataset Assembly",
                "module": "explorer_analysis.py",
                "description": "Group enriched rows into post-level and language-level structures for chart-ready output.",
            },
            {
                "title": "5. Insight Views",
                "module": "explorer.html / advanced_analysis.html",
                "description": "Render exploratory charts, direct row previews, and drill-downs from the enriched dataset.",
            },
        ],
        "implementation_notes": [
            "Use the `Comments` table as the source of truth for filtering and retrieval.",
            "Move heavy processing into explicit backend stages or precomputed tables.",
            "Keep chart clicks connected to raw comments for validation.",
            "Use the FAQ page as product and technical reference for future contributors.",
        ],
        "advanced_filters": [
            {
                "name": "Page name",
                "meaning": "Restricts the dataset to one or more display names from `EnrichedComments.PageName`.",
            },
            {
                "name": "Page id",
                "meaning": "Restricts the dataset to one or more stable page identifiers from `EnrichedComments.PageID`.",
            },
            {
                "name": "Source",
                "meaning": "Keeps only rows loaded from the selected ingestion source or loader lineage value.",
            },
            {
                "name": "Main language",
                "meaning": "Limits rows to comments whose detected dominant language matches the selected values.",
            },
            {
                "name": "Sentiment",
                "meaning": "Filters individual comments by their own sentiment label: positive, neutral, or negative.",
            },
            {
                "name": "Post description sentiment",
                "meaning": "Filters posts by the sentiment of the first comment in the full unfiltered post, used as the post anchor.",
            },
            {
                "name": "Minimum comment likes",
                "meaning": "Keeps only comments whose `CommentLikes` value is greater than or equal to the chosen threshold.",
            },
            {
                "name": "Post time from / to",
                "meaning": "Restricts the subset by the publication time of the post itself, not the comment time.",
            },
            {
                "name": "Comment time from / to",
                "meaning": "Restricts the subset by when the comment was created, useful for response-window analysis.",
            },
            {
                "name": "Comment text search",
                "meaning": "Matches rows where the raw comment text or filtered comment text contains the given phrase or keyword.",
            },
        ],
    }

    return render_template(
        'faq.html',
        current_user=current_user,
        page_sections=page_sections,
        faq_reference=faq_reference,
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
        instagram_login = data.get('instagram_login')
        instagram_password = data.get('instagram_password')

        if not username or not password or not email or not instagram_login or not instagram_password:
            return jsonify({'error': 'All fields are required'}), 400

        password_hash = hashlib.sha256(password.encode()).hexdigest()

        return insert_new_user(username, email, password_hash, instagram_login, instagram_password)
    return None


@app.route('/process-data', methods=['POST'])
@jwt_required()
def process_data_endpoint():
    try:
        current_user = get_jwt_identity()
        params = request.json.get('params', {})
        target_page = params["param1"]
        number_of_posts = int(params["param2"])

        if not params:
            return jsonify({'error': 'No parameters provided.'}), 400

        instagram_credentials = fetch_user_instagram_credentials(current_user)
        if not instagram_credentials:
            return jsonify({'error': 'Logged in user was not found.'}), 404

        instagram_username = instagram_credentials.get('instagram_login')
        instagram_password = instagram_credentials.get('instagram_password')

        if not instagram_username or not instagram_password:
            return jsonify({'error': 'Instagram credentials are missing for the logged in user.'}), 400

        existing_post_hrefs = fetch_existing_post_hrefs(target_page)
        logger.debug(
            "Found %s existing post hrefs for page_id=%s before extraction",
            len(existing_post_hrefs),
            target_page,
        )

        extraction_result = extract_data(
            instagram_username,
            instagram_password,
            target_page,
            number_of_posts,
            existing_post_hrefs=existing_post_hrefs,
        )
        if extraction_result.get('new_posts_found', 0) == 0:
            return jsonify(
                {
                    'success': True,
                    'result': {
                        'target_page': target_page,
                        'posts_requested': number_of_posts,
                        'posts_loaded': 0,
                        'comments_collected': 0,
                        'rows_loaded_to_db': 0,
                        'files_processed': 0,
                        'message': 'No new posts found. Existing database posts were skipped.',
                    }
                }
            ), 200
        if extraction_result.get('posts_loaded', 0) == 0 or not extraction_result.get('saved_files'):
            return jsonify(
                {
                    'error': 'Extraction did not produce any files.',
                    'result': extraction_result,
                }
            ), 502

        logger.debug("Starting load_to_db after extract_data")
        load_result = load_to_db(dry_run=False)
        logger.debug("load_to_db finished")


        return jsonify(
            {
                'success': True,
                'result': {
                    'target_page': target_page,
                    'posts_requested': number_of_posts,
                    'posts_loaded': extraction_result.get('posts_loaded', 0),
                    'comments_collected': extraction_result.get('comments_collected', 0),
                    'rows_loaded_to_db': load_result.get('rows_loaded', 0),
                    'files_processed': load_result.get('files_processed', 0),
                }
            }
        ), 200
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
        logger.info(
            "enrich-comments finished: mode=%s selected=%s processed=%s added=%s updated=%s deleted=%s page_name=%s page_id=%s",
            result.get('mode'),
            result.get('selected'),
            result.get('processed'),
            result.get('added_count', 0),
            result.get('updated_count', 0),
            result.get('deleted', 0),
            result.get('page_name'),
            result.get('page_id'),
        )
        return jsonify({'success': True, 'result': result}), 200
    except Exception as e:
        logger.exception("enrich-comments failed")
        return jsonify({'error': str(e)}), 500


@app.route('/page-analysis', methods=['POST'])
@jwt_required()
def page_analysis_endpoint():
    try:
        data = request.json or {}
        selection_type = data.get('selection_type')
        selection_value = data.get('selection_value')
        result = build_page_analysis(selection_type=selection_type, selection_value=selection_value)
        logger.info(
            "page-analysis finished: selection_type=%s selection_value=%s total_comments=%s posts=%s",
            selection_type,
            selection_value,
            result.get('summary', {}).get('total_comments') if result.get('summary') else 0,
            result.get('summary', {}).get('distinct_posts') if result.get('summary') else 0,
        )
        return jsonify({'success': True, 'result': result}), 200
    except Exception as e:
        logger.exception("page-analysis failed")
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
