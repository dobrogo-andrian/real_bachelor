# Real Bachelor Project

`real_bachelor` is a Flask application for collecting Instagram comments, loading them into SQL Server, enriching them with language and sentiment metadata, and exploring the result through authenticated web pages.

## What the project does

- Authenticates users with JWT cookies.
- Stores application users, encrypted Instagram credentials, and per-user protected Instagram session cookies in SQL Server.
- Stores application passwords as adaptive `scrypt` hashes and upgrades legacy SHA-256 hashes on successful login.
- Runs an Instagram extraction workflow with Selenium and ChromeDriver.
- Loads scraped CSV files into a `Comments` table.
- Builds an `EnrichedComments` layer with language detection and sentiment scoring.
- Serves explorer and advanced-analysis pages backed by filtered database queries.

## Main application flow

1. A user signs up through `/signup`, which stores the app password hash and encrypted Instagram credentials.
2. The user logs in through `/login`, which sets JWT access and refresh cookies.
3. The extractor page calls `/process-data`, which:
   - fetches the logged-in user's Instagram credentials,
   - runs `extract_data(...)`,
   - reuses that user's signed Instagram session cookies when available, otherwise waits for manual login in the opened browser window and then updates the stored cookie payload,
   - aborts the run if Instagram shows a restriction or challenge page,
   - loads discovered CSV files from `unprocessed_data/` into SQL Server with `load_to_db(...)`.
4. The user can call `/enrich-comments` to populate or refresh `EnrichedComments`.
5. The explorer and advanced-analysis pages query enriched rows and build chart-ready summaries.

## Key routes

- Public pages: `/`, `/login`, `/signup`, `/test`
- Authenticated pages: `/extractor`, `/explorer`, `/advanced-analysis`, `/faq`, `/elements`, `/account`
- API endpoints:
  - `/refresh`
  - `/logout`
  - `/user-info`
  - `/submit-form`
  - `/process-data`
  - `/enrich-comments`
  - `/page-analysis`
  - `/api/advanced-analysis/preview`
  - `/api/advanced-analysis/analyze`

## Repository map

- `app.py`: Flask entrypoint, route definitions, JWT handling, and orchestration of extraction/loading/enrichment/analysis.
- `static/backend/`: Python backend modules and page-specific frontend scripts.
- `templates/`: Jinja/HTML pages for login, signup, account management, extractor, explorer, advanced analysis, FAQ, and landing pages.
- `static/assets/`: HTML5UP "Forty" theme assets plus project CSS.
- `ddl/`: SQL Server table definitions for `Users`, `Comments`, and `EnrichedComments`.
- `unprocessed_data/`: generated raw CSV files from extraction jobs.
Detailed structure notes live in `PROJECT_STRUCTURE.md`.

## Requirements

Python packages are listed in `requirements.txt`:

- `flask`
- `flask-cors`
- `flask-jwt-extended`
- `pyodbc`
- `selenium`
- `fake-useragent`
- `pandas`
- `langdetect`
- `transformers`
- `seaborn`
- `matplotlib`
- `statsmodels`

External dependencies:

- Windows machine with DPAPI support for credential encryption in `db_connection.py`
- SQL Server with ODBC Driver 17
- Chrome installed
- ChromeDriver available at the path expected by `static/backend/extract_data.py`
- Network access for Instagram scraping and Hugging Face model downloads

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a local `.env` file.
   - `.env.example` lists the required variables.
   - `.env` is loaded automatically on app startup.
   - Set at least `JWT_SECRET_KEY`, `DB_SERVER`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
   - Optionally set `COOKIE_SIGNING_SECRET`; if omitted, signed Instagram cookie payloads fall back to `JWT_SECRET_KEY`.
4. Create the SQL Server database and tables from:
   - `ddl/Users.sql`
   - `ddl/Users_AddInstagramCookies.sql` for existing databases that need the new cookie columns
   - `ddl/Comments.sql`
   - `ddl/EnrichedComments.sql`
   - For an existing database, apply `ddl/migrations/001_harden_users_password_storage.sql`.
5. Update `CHROMEDRIVER_PATH` in `.env` if ChromeDriver is not on your PATH.
6. Start the Flask app:

```bash
python app.py
```

The app runs on `http://localhost:5000`.

## Data model

- `Users`: application users plus email-verification metadata, encrypted Instagram credentials, and per-user protected Instagram session cookies.
- `Comments`: raw ingested comments keyed by `CommentHash`.
- `EnrichedComments`: language-processed and sentiment-scored comments keyed by the same `CommentHash`.

## Operational notes

- The scraper writes CSV files under `unprocessed_data/`.
- `load_to_db()` reads every CSV under `unprocessed_data/` recursively.
- `enrich_comments()` supports scoped processing by mode, page name, or page id.
- Advanced analysis supports filters for page, source, language, sentiment, likes, time windows, first-comment sentiment, and text search.

## Current caveats

- `static/backend/extract_data.py` uses optional `.env` variables for its standalone `__main__` entrypoint.
- Generated directories such as `__pycache__/` and `unprocessed_data/` are currently present in the repository worktree.

## License

Frontend assets are based on HTML5UP "Forty" and are covered by the attribution/license text in `LICENSE.txt`.
