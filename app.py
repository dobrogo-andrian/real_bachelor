import os
import logging
import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from functools import wraps

os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from env_config import load_dotenv, get_app_environment, get_bool_env, get_cookie_samesite, get_int_env, get_list_env

load_dotenv()

from flask import Flask, request, jsonify, redirect, url_for, render_template, send_from_directory, make_response
from static.backend.extract_data import extract_data
from static.backend.faq_content import FAQ_REFERENCE, PAGE_SECTIONS
from static.backend.load_to_db import load_row_batches
from static.backend.enrich_comments import enrich_comments
from static.backend.explorer_analysis import build_page_analysis, build_analysis_from_rows
from static.backend.job_queue import job_queue
from static.backend.db_connection import (
    build_enriched_comment_preview_from_rows,
    clear_user_instagram_cookies,
    fetch_account_statistics,
    insert_new_user,
    fetch_user,
    fetch_user_profile,
    fetch_user_instagram_credentials,
    fetch_distinct_comment_dimensions,
    fetch_existing_post_hrefs,
    fetch_advanced_comment_dimensions,
    fetch_enriched_comment_rows,
    get_db_connection,
    set_user_email_verified,
    update_user_password_hash,
    update_user_instagram_credentials,
)
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, set_access_cookies, set_refresh_cookies,
    unset_jwt_cookies
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__, static_folder=None)
app_environment = get_app_environment()
is_production = app_environment == 'production'
debug_enabled = get_bool_env('DEBUG', default=not is_production)
jwt_cookie_secure = get_bool_env('JWT_COOKIE_SECURE', default=is_production)
jwt_cookie_samesite = get_cookie_samesite(default='Lax')
cors_allowed_origins = get_list_env(
    'CORS_ALLOWED_ORIGINS',
    default=['http://localhost:5000', 'http://127.0.0.1:5000'],
)

app.config['JWT_SECRET_KEY'] = os.environ['JWT_SECRET_KEY']
app.config['APP_ENV'] = app_environment
app.config['DEBUG'] = debug_enabled
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_SECURE'] = jwt_cookie_secure
app.config['JWT_COOKIE_SAMESITE'] = jwt_cookie_samesite
app.config['CORS_ALLOWED_ORIGINS'] = cors_allowed_origins
app.config['TRUST_PROXY_HEADERS'] = get_bool_env('TRUST_PROXY_HEADERS', default=False)
app.config['JWT_ACCESS_COOKIE_PATH'] = '/'
app.config['JWT_REFRESH_COOKIE_PATH'] = '/refresh'
app.config['JWT_COOKIE_CSRF_PROTECT'] = True
app.config['RATE_LIMIT_LOGIN_MAX_ATTEMPTS'] = get_int_env('RATE_LIMIT_LOGIN_MAX_ATTEMPTS', 10)
app.config['RATE_LIMIT_LOGIN_WINDOW_SECONDS'] = get_int_env('RATE_LIMIT_LOGIN_WINDOW_SECONDS', 60)
app.config['RATE_LIMIT_PROCESS_DATA_MAX_ATTEMPTS'] = get_int_env('RATE_LIMIT_PROCESS_DATA_MAX_ATTEMPTS', 10)
app.config['RATE_LIMIT_PROCESS_DATA_WINDOW_SECONDS'] = get_int_env('RATE_LIMIT_PROCESS_DATA_WINDOW_SECONDS', 60)
app.config['RATE_LIMIT_ENRICH_COMMENTS_MAX_ATTEMPTS'] = get_int_env('RATE_LIMIT_ENRICH_COMMENTS_MAX_ATTEMPTS', 10)
app.config['RATE_LIMIT_ENRICH_COMMENTS_WINDOW_SECONDS'] = get_int_env('RATE_LIMIT_ENRICH_COMMENTS_WINDOW_SECONDS', 60)
app.config['RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS'] = get_int_env('RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS', 60)
app.config['RATE_LIMIT_ANALYSIS_WINDOW_SECONDS'] = get_int_env('RATE_LIMIT_ANALYSIS_WINDOW_SECONDS', 60)
app.config['ENABLE_BACKGROUND_JOBS'] = get_bool_env('ENABLE_BACKGROUND_JOBS', default=False)
logging.basicConfig(level=logging.DEBUG if debug_enabled else logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG if debug_enabled else logging.INFO)
logger.debug("Application started.")

logging.getLogger("selenium").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
CORS(
    app,
    resources={r"/*": {"origins": cors_allowed_origins}},
    supports_credentials=True,
)
jwt = JWTManager(app)
rate_limit_storage = defaultdict(deque)
rate_limit_lock = threading.Lock()


def _is_csrf_error(error):
    return isinstance(error, str) and 'csrf' in error.lower()


def hash_user_password(password):
    return generate_password_hash(password, method='scrypt')


def _is_legacy_sha256_hash(value):
    return isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value.lower())


def verify_user_password(stored_password_hash, provided_password):
    if not stored_password_hash or provided_password is None:
        return False, None

    if _is_legacy_sha256_hash(stored_password_hash):
        legacy_hash = hashlib.sha256(provided_password.encode()).hexdigest()
        if hmac.compare_digest(stored_password_hash, legacy_hash):
            return True, hash_user_password(provided_password)
        return False, None

    return check_password_hash(stored_password_hash, provided_password), None


def verify_application_password(username, provided_password):
    user = fetch_user(username)
    if not user:
        return False

    password_valid, upgraded_password_hash = verify_user_password(user[0], provided_password)
    if password_valid and upgraded_password_hash:
        update_user_password_hash(username, upgraded_password_hash)
    return password_valid


DUMMY_PASSWORD_HASH = hash_user_password('not-the-user-password')


def mask_secret_for_hint(secret):
    if not secret:
        return "Not configured"
    if len(secret) <= 2:
        return "*" * len(secret)
    return f"{secret[0]}{'*' * (len(secret) - 2)}{secret[-1]}"


def _get_request_client_identifier():
    if app.config.get('TRUST_PROXY_HEADERS'):
        forwarded_for = request.headers.get('X-Forwarded-For', '')
        if forwarded_for:
            client_ip = forwarded_for.split(',', 1)[0].strip()
            if client_ip:
                return client_ip
    return request.remote_addr or 'unknown'


def clear_rate_limit_state():
    with rate_limit_lock:
        rate_limit_storage.clear()


def _consume_rate_limit(bucket_name, bucket_key, max_attempts, window_seconds):
    now = time.time()
    window_start = now - window_seconds
    storage_key = (bucket_name, bucket_key)

    with rate_limit_lock:
        attempts = rate_limit_storage[storage_key]
        while attempts and attempts[0] <= window_start:
            attempts.popleft()

        if len(attempts) >= max_attempts:
            retry_after = max(1, int(attempts[0] + window_seconds - now))
            return retry_after

        attempts.append(now)
        return None


def _rate_limit_exceeded_response(scope, retry_after):
    response = jsonify(
        {
            'error': f'Too many {scope} requests. Please retry later.',
            'retry_after_seconds': retry_after,
        }
    )
    response.headers['Retry-After'] = str(retry_after)
    return response, 429


def _internal_error_response(client_message):
    return jsonify({'error': client_message}), 500


def _job_response(job_id):
    return jsonify({'job_id': job_id, 'status': 'queued'}), 202


def limit_requests(bucket_name, max_attempts_config_key, window_seconds_config_key, key_builder, scope):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            bucket_key = key_builder()
            retry_after = _consume_rate_limit(
                bucket_name,
                bucket_key,
                app.config[max_attempts_config_key],
                app.config[window_seconds_config_key],
            )
            if retry_after is not None:
                logger.warning(
                    "Rate limit exceeded: bucket=%s key=%s retry_after=%s",
                    bucket_name,
                    bucket_key,
                    retry_after,
                )
                return _rate_limit_exceeded_response(scope, retry_after)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def _build_login_rate_limit_key():
    data = request.get_json(silent=True) or {}
    username = str(data.get('username', '')).strip().lower() or 'anonymous'
    client_id = _get_request_client_identifier()
    return f'{client_id}:{username}'


@app.route('/jobs/<job_id>', methods=['GET'])
@jwt_required()
def job_status(job_id):
    job = job_queue.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found.'}), 404
    return jsonify(job), 200


def _run_process_data(current_user, params):
    target_page = str(params.get("param1", "")).strip()
    number_of_posts = int(params.get("param2"))
    headless_session_only = bool(params.get("headless_session_only"))

    instagram_credentials = fetch_user_instagram_credentials(current_user)
    if not instagram_credentials:
        return {'error': 'Logged in user was not found.'}, 404

    instagram_username = instagram_credentials.get('instagram_login')
    instagram_password = instagram_credentials.get('instagram_password')
    if not instagram_username or not instagram_password:
        return {'error': 'Instagram credentials are missing for the logged in user.'}, 400

    existing_post_hrefs = fetch_existing_post_hrefs(target_page)
    logger.debug(
        "Found %s existing post hrefs for page_id=%s before extraction",
        len(existing_post_hrefs),
        target_page,
    )

    db_conn = None

    def persist_comment_batch(rows):
        nonlocal db_conn
        if not rows:
            return 0
        if db_conn is None:
            db_conn = get_db_connection()
        load_result = load_row_batches([rows], dry_run=False, conn=db_conn)
        return load_result.get('rows_loaded', 0)

    try:
        extraction_result = extract_data(
            instagram_username,
            instagram_password,
            target_page,
            number_of_posts,
            existing_post_hrefs=existing_post_hrefs,
            app_username=current_user,
            headless_session_only=headless_session_only,
            comment_batch_handler=persist_comment_batch,
        )
    finally:
        if db_conn is not None:
            db_conn.close()
    if extraction_result.get('aborted_reason'):
        return {
            'error': extraction_result['aborted_reason'],
            'result': extraction_result,
        }, 409
    if extraction_result.get('new_posts_found', 0) == 0:
        return {
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
        }, 200
    if extraction_result.get('posts_loaded', 0) == 0:
        return {
            'error': 'Extraction did not produce any post batches.',
            'result': extraction_result,
        }, 502

    return {
        'success': True,
        'result': {
            'target_page': target_page,
            'posts_requested': number_of_posts,
            'posts_loaded': extraction_result.get('posts_loaded', 0),
            'comments_collected': extraction_result.get('comments_collected', 0),
            'rows_loaded_to_db': extraction_result.get('rows_loaded_to_db', 0),
            'files_processed': extraction_result.get('batches_loaded_to_db', 0),
        }
    }, 200


def _run_enrich_comments(mode, page_name=None, page_id=None):
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
    return {'success': True, 'result': result}, 200


@app.route('/static/<path:filename>')
def static_proxy(filename):
    return send_from_directory('static', filename)


@app.before_request
def log_request():
    if request.path.startswith('/static/') or request.path == '/favicon.ico':
        return
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
        retry_after = _consume_rate_limit(
            'login',
            _build_login_rate_limit_key(),
            app.config['RATE_LIMIT_LOGIN_MAX_ATTEMPTS'],
            app.config['RATE_LIMIT_LOGIN_WINDOW_SECONDS'],
        )
        if retry_after is not None:
            return _rate_limit_exceeded_response('login', retry_after)

        data = request.json
        username = data['username']
        password = data['password']

        user = fetch_user(username)
        if not user:
            verify_user_password(DUMMY_PASSWORD_HASH, password)
            return jsonify({'error': 'Invalid username or password'}), 401

        stored_password_hash = user[0]
        password_valid, upgraded_password_hash = verify_user_password(stored_password_hash, password)
        if password_valid:
            if upgraded_password_hash:
                update_user_password_hash(username, upgraded_password_hash)
            access_token = create_access_token(identity=username)
            refresh_token = create_refresh_token(identity=username)

            response = jsonify({'message': 'Login successful'})
            set_access_cookies(response, access_token)
            set_refresh_cookies(response, refresh_token)
            return response, 200
        return jsonify({'error': 'Invalid username or password'}), 401
    return None


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    response = jsonify({'message': 'Logout successful'})
    unset_jwt_cookies(response)
    return response, 200


@app.route('/user-info')
@jwt_required()
def user_info():
    current_user = get_jwt_identity()
    profile = fetch_user_profile(current_user)
    if not profile:
        return jsonify({'error': 'User not found'}), 404
    return jsonify(username=current_user, email=profile['email'])


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


@app.route('/api/extractor/page-dimensions')
@jwt_required()
def extractor_page_dimensions():
    try:
        return jsonify(fetch_distinct_comment_dimensions()), 200
    except Exception:
        logger.exception("Failed to load extractor page dimensions.")
        return _internal_error_response("Failed to load distinct page values.")


@app.route('/account')
@jwt_required()
def account():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template('account.html', current_user=current_user)


@app.route('/api/account')
@jwt_required()
def account_details():
    current_user = get_jwt_identity()
    profile = fetch_user_profile(current_user)
    if not profile:
        return jsonify({'error': 'User not found'}), 404

    return jsonify(
        {
            'profile': profile,
            'stats': fetch_account_statistics(),
        }
    )


@app.route('/api/account/manual-login-hint')
@jwt_required()
def account_manual_login_hint():
    current_user = get_jwt_identity()
    instagram_credentials = fetch_user_instagram_credentials(current_user)
    if not instagram_credentials:
        return jsonify({'error': 'Instagram credentials are not configured for this user.'}), 404

    instagram_login = instagram_credentials.get('instagram_login')
    instagram_password = instagram_credentials.get('instagram_password')
    return jsonify(
        {
            'instagram_login': instagram_login or '',
            'instagram_password_hint': mask_secret_for_hint(instagram_password or ''),
        }
    ), 200


@app.route('/api/account/change-password', methods=['POST'])
@jwt_required()
def account_change_password():
    current_user = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'Current password and new password are required.'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters long.'}), 400
    if not verify_application_password(current_user, current_password):
        return jsonify({'error': 'Current password is incorrect.'}), 401

    update_user_password_hash(current_user, hash_user_password(new_password))
    return jsonify({'message': 'Password updated successfully.'}), 200


@app.route('/api/account/verify-email', methods=['POST'])
@jwt_required()
def account_verify_email():
    current_user = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password', '')
    if not current_password:
        return jsonify({'error': 'Current password is required.'}), 400
    if not verify_application_password(current_user, current_password):
        return jsonify({'error': 'Current password is incorrect.'}), 401

    set_user_email_verified(current_user, True)
    return jsonify({'message': 'Email marked as verified for this local account.'}), 200


@app.route('/api/account/instagram-cookies/clear', methods=['POST'])
@jwt_required()
def account_clear_instagram_cookies():
    current_user = get_jwt_identity()
    clear_user_instagram_cookies(current_user)
    return jsonify({'message': 'Stored Instagram cookies cleared.'}), 200


@app.route('/api/account/instagram-credentials', methods=['POST'])
@jwt_required()
def account_update_instagram_credentials():
    current_user = get_jwt_identity()
    data = request.get_json(silent=True) or {}
    instagram_login = (data.get('instagram_login') or '').strip()
    instagram_password = data.get('instagram_password') or ''
    if not instagram_login or not instagram_password:
        return jsonify({'error': 'Instagram login and password are required.'}), 400

    update_user_instagram_credentials(current_user, instagram_login, instagram_password)
    return jsonify({'message': 'Instagram credentials updated. Stored Instagram cookies were cleared.'}), 200


@app.route('/api/account/instagram-credentials', methods=['DELETE'])
@jwt_required()
def account_delete_instagram_credentials():
    current_user = get_jwt_identity()
    update_user_instagram_credentials(current_user, None, None)
    return jsonify({'message': 'Instagram credentials deleted and stored cookies cleared.'}), 200


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
    except Exception:
        logger.exception("Failed to load distinct page dimensions for explorer.")
        page_loading_error = "Could not load page lists right now."

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
    except Exception:
        logger.exception("Failed to load advanced analysis dimensions.")
        page_loading_error = "Could not load advanced-analysis filters right now."

    return render_template(
        'advanced_analysis.html',
        current_user=current_user,
        advanced_dimensions=advanced_dimensions,
        page_loading_error=page_loading_error,
    )


@app.route('/api/advanced-analysis/preview', methods=['POST'])
@jwt_required()
@limit_requests(
    bucket_name='analysis',
    max_attempts_config_key='RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS',
    window_seconds_config_key='RATE_LIMIT_ANALYSIS_WINDOW_SECONDS',
    key_builder=lambda: get_jwt_identity(),
    scope='analysis',
)
def advanced_analysis_preview():
    payload = request.get_json(silent=True) or {}
    logger.debug("Advanced analysis preview payload: %s", payload)
    try:
        analysis_rows = fetch_enriched_comment_rows(payload)
        preview = build_enriched_comment_preview_from_rows(analysis_rows, payload, limit=100)
        analysis = build_analysis_from_rows(
            analysis_rows,
            selection_type="advanced_filters",
            selection_value="filtered_subset",
            filters=payload,
        )
        preview["analysis"] = analysis
        return jsonify(preview), 200
    except Exception:
        logger.exception("Failed to fetch advanced analysis preview.")
        return _internal_error_response("Failed to load advanced analysis preview.")


@app.route('/api/advanced-analysis/analyze', methods=['POST'])
@jwt_required()
@limit_requests(
    bucket_name='analysis',
    max_attempts_config_key='RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS',
    window_seconds_config_key='RATE_LIMIT_ANALYSIS_WINDOW_SECONDS',
    key_builder=lambda: get_jwt_identity(),
    scope='analysis',
)
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
    except Exception:
        logger.exception("Failed to build advanced analysis charts.")
        return _internal_error_response("Failed to build advanced analysis.")


@app.route('/faq')
@jwt_required()
def faq():
    current_user = get_jwt_identity()
    logger.debug(f"Current user: {current_user}")
    return render_template(
        'faq.html',
        current_user=current_user,
        page_sections=PAGE_SECTIONS,
        faq_reference=FAQ_REFERENCE,
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

        password_hash = hash_user_password(password)

        return insert_new_user(username, email, password_hash, instagram_login, instagram_password)
    return None


@app.route('/process-data', methods=['POST'])
@jwt_required()
@limit_requests(
    bucket_name='process-data',
    max_attempts_config_key='RATE_LIMIT_PROCESS_DATA_MAX_ATTEMPTS',
    window_seconds_config_key='RATE_LIMIT_PROCESS_DATA_WINDOW_SECONDS',
    key_builder=lambda: get_jwt_identity(),
    scope='process-data',
)
def process_data_endpoint():
    try:
        current_user = get_jwt_identity()
        data = request.get_json(silent=True) or {}
        params = data.get('params')

        if not isinstance(params, dict) or not params:
            return jsonify({'error': 'No parameters provided.'}), 400

        target_page = str(params.get("param1", "")).strip()
        if not target_page:
            return jsonify({'error': 'Target page is required.'}), 400

        raw_number_of_posts = params.get("param2")
        if raw_number_of_posts in (None, ""):
            return jsonify({'error': 'Number of posts is required.'}), 400

        headless_session_only = bool(params.get("headless_session_only"))

        try:
            number_of_posts = int(raw_number_of_posts)
        except (TypeError, ValueError):
            return jsonify({'error': 'Number of posts must be an integer.'}), 400

        if number_of_posts <= 0:
            return jsonify({'error': 'Number of posts must be greater than zero.'}), 400

        if app.config['ENABLE_BACKGROUND_JOBS']:
            job_id = job_queue.submit(_run_process_data, current_user, params)
            return _job_response(job_id)

        payload, status_code = _run_process_data(current_user, params)
        return jsonify(payload), status_code
    except Exception:
        logger.exception("process-data failed")
        return _internal_error_response('Process-data request failed.')


@app.route('/enrich-comments', methods=['POST'])
@jwt_required()
@limit_requests(
    bucket_name='enrich-comments',
    max_attempts_config_key='RATE_LIMIT_ENRICH_COMMENTS_MAX_ATTEMPTS',
    window_seconds_config_key='RATE_LIMIT_ENRICH_COMMENTS_WINDOW_SECONDS',
    key_builder=lambda: get_jwt_identity(),
    scope='enrich-comments',
)
def enrich_comments_endpoint():
    try:
        data = request.json or {}
        mode = data.get('mode')
        page_name = data.get('page_name')
        page_id = data.get('page_id')

        if app.config['ENABLE_BACKGROUND_JOBS']:
            job_id = job_queue.submit(_run_enrich_comments, mode, page_name, page_id)
            return _job_response(job_id)

        payload, status_code = _run_enrich_comments(mode, page_name=page_name, page_id=page_id)
        return jsonify(payload), status_code
    except Exception:
        logger.exception("enrich-comments failed")
        return _internal_error_response('Enrich-comments request failed.')


@app.route('/page-analysis', methods=['POST'])
@jwt_required()
@limit_requests(
    bucket_name='analysis',
    max_attempts_config_key='RATE_LIMIT_ANALYSIS_MAX_ATTEMPTS',
    window_seconds_config_key='RATE_LIMIT_ANALYSIS_WINDOW_SECONDS',
    key_builder=lambda: get_jwt_identity(),
    scope='analysis',
)
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
    except Exception:
        logger.exception("page-analysis failed")
        return _internal_error_response('Page-analysis request failed.')


@jwt.invalid_token_loader
def invalid_token_callback(error):
    logger.debug(f"Invalid token error: {error}")
    if _is_csrf_error(error):
        return jsonify({"error": error, "action": "logout"}), 401
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
    if _is_csrf_error(error):
        return jsonify({"error": error, "action": "logout"}), 401
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
    app.run(debug=debug_enabled, port=5000)
