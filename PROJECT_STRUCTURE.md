# Project Structure and Purpose

This repository is a Flask-based web application with a static HTML frontend and a set of Python scripts for social media comment collection and analysis. The Flask app handles authentication (JWT cookies), serves HTML templates, and exposes API endpoints. The `static/backend` scripts implement a data pipeline: scrape Instagram comments, clean/language-detect, run sentiment analysis, aggregate into a dataset, and visualize results.

## High-Level Architecture
- **Web app (Flask)**: `app.py` is the entrypoint; serves templates and JSON endpoints, manages JWT auth via cookies.
- **Frontend (HTML/CSS/JS)**: `templates/` for pages and `static/assets/` for styles, images, JS (based on HTML5UP "Forty").
- **Data pipeline scripts**: `static/backend/*.py` for scraping, cleaning, sentiment analysis, aggregation, and visualization.
- **Database access**: `static/backend/db_connection.py` connects to a local SQL Server database for users.

## Key Entry Points
- **`app.py`**: Flask app. Routes for login/signup/logout, JWT cookie refresh, static proxy, and data-processing endpoint.
- **`static/backend/load_data.py`**: Selenium-based scraper for Instagram comments; writes CSVs.
- **`static/backend/process_data.py`**: Cleans comments, detects main language, writes filtered CSVs.
- **`static/backend/analyze_data.py`**: Sentiment analysis by language using Hugging Face transformers pipelines.
- **`static/backend/agregate_data.py`**: Merges analyzed CSVs into a single dataset with IDs.
- **`static/backend/visualize_data.py`**: Exploratory analysis and plots with seaborn/matplotlib.

## Repository Layout
- `app.py`
  - Flask app and API routes.
- `templates/`
  - `index.html`, `landing.html`, `elements.html`, `generic.html`, `login.html`, `signup.html`, `test.html`
- `static/`
  - `assets/`
    - `css/`, `js/`, `images/`, `sass/`, `webfonts/` (HTML5UP "Forty" theme assets)
  - `backend/`
    - `load_data.py` (scrape comments with Selenium)
    - `process_data.py` (language filtering/cleaning)
    - `analyze_data.py` (sentiment analysis)
    - `agregate_data.py` (dataset aggregation)
    - `visualize_data.py` (EDA/plots)
    - `db_connection.py` (SQL Server user DB)
    - `auth/` (legacy JS auth logic)
    - `cookie/` (cookie pickle used by scraper)
    - `unprocessed_data/` (raw CSV output, example `comments1/`)

## Web App Behavior
- **Auth**
  - JWT cookies stored by Flask-JWT-Extended.
  - CSRF protection is disabled.
  - `JWT_SECRET_KEY` is hardcoded in `app.py`.
  - `/login` returns JSON on POST and sets access/refresh cookies.
  - `/refresh` issues new access token from refresh cookie.
  - Protected routes use `@jwt_required()`.
  - Invalid/expired/absent tokens redirect to login for HTML requests and return JSON for API requests.
- **Routes**
  - `/`, `/test`, `/login`, `/signup` serve templates.
  - `/elements`, `/generic`, `/landing`, `/static/<path>` are JWT-protected.
  - `/process-data` triggers the scraper and returns basic JSON.

## Data Pipeline (Expected Flow)
1. **Scrape**: `load_data.py` uses Selenium to log in, find posts, and save comments to `static/backend/unprocessed_data/comments1/*.csv`.
2. **Filter by language**: `process_data.py` reads raw CSVs, filters text, and writes to `language_marked_comments/...`.
3. **Sentiment**: `analyze_data.py` loads transformer models and writes sentiment-labeled CSVs to `sentiment_analysis/...`.
4. **Aggregate**: `agregate_data.py` merges CSVs into `final_dataset/.../combined_comments_*.csv`.
5. **Visualize**: `visualize_data.py` reads the final dataset and produces plots.

## Notable Implementation Details and Risks
- **Side effects on import**: `static/backend/load_data.py` ends with a call to `load_data(...)` using hardcoded Instagram credentials. Importing this module will run the scraper immediately.
- **Hardcoded secrets/paths**:
  - `JWT_SECRET_KEY` is a placeholder in `app.py`.
  - Selenium ChromeDriver path is hardcoded to `C:\chromedriver\chromedriver-win64\chromedriver.exe`.
  - `load_data.py` embeds a username/password at the bottom.
- **Database**: `db_connection.py` expects a local SQL Server instance and `Users` table. `insert_data_to_database` currently duplicates user-insert logic and references undefined variables (`username`, `email`, `password`).
- **Encoding**: Several comments/log strings in pipeline scripts contain mojibake, likely from non-UTF-8 encoding in source files.
- **Frontend auth JS**: `static/backend/auth/*.js` appears unused by Flask routes, likely legacy.

## How to Extend Safely
- Add a `README.md` or update `README.txt` with setup steps and environment variables.
- Move secrets and credentials to environment variables.
- Remove the `load_data(...)` call at module import and guard it with `if __name__ == "__main__":`.
- Define and document expected data directories (`language_marked_comments`, `sentiment_analysis`, `final_dataset`) if they should be checked in or generated.

## Dependencies (Inferred from Code)
- Python packages: `flask`, `flask-cors`, `flask-jwt-extended`, `pyodbc`, `selenium`, `fake-useragent`, `pandas`, `langdetect`, `transformers`, `seaborn`, `matplotlib`, `statsmodels`.
- External: ChromeDriver, SQL Server (ODBC Driver 17), Hugging Face model downloads at runtime.
