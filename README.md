# Real Bachelor Project

`real_bachelor` is a Flask application for collecting Instagram comments, loading them into SQL Server, enriching them with language and sentiment metadata, and exploring the result through authenticated web pages.

Full local deployment instructions are available in `DEPLOYMENT.md`.

## What the project does

- Authenticates users with JWT cookies.
- Stores application users, encrypted Instagram credentials, and per-user protected Instagram session cookies in SQL Server.
- Stores application passwords as adaptive `scrypt` hashes and upgrades legacy SHA-256 hashes on successful login.
- Runs an Instagram extraction workflow with Selenium and ChromeDriver.
- Streams scraped comment batches directly into the `Comments` table.
- Builds an `EnrichedComments` layer with batched language detection and Hugging Face sentiment inference.
- Serves explorer and advanced-analysis pages backed by filtered database queries.
- Includes a local fine-tuning workspace for LoRA-based sentiment adapters.

## Main application flow

1. A user signs up through `/signup`, which stores the app password hash and encrypted Instagram credentials.
2. The user logs in through `/login`, which sets JWT access and refresh cookies.
3. The extractor page calls `/process-data`, which:
   - fetches the logged-in user's Instagram credentials,
   - runs `extract_data(...)`,
   - reuses that user's signed Instagram session cookies when available, otherwise waits for manual login in the opened browser window and then updates the stored cookie payload,
   - aborts the run if Instagram shows a restriction or challenge page,
   - streams each extracted post's comment batch directly into SQL Server through bounded loader batches.
4. The user can call `/enrich-comments` to populate or refresh `EnrichedComments`.
   - delta mode reads raw comments on one DB connection and writes enriched rows on a separate DB connection to avoid ODBC streaming conflicts.
   - sentiment inference is executed in batches rather than one comment at a time.
5. The explorer and advanced-analysis pages query enriched rows and build chart-ready summaries.

If `ENABLE_BACKGROUND_JOBS=true`, `/process-data` and `/enrich-comments` return `202` plus a `job_id`, and the client polls `/jobs/<job_id>` until completion.

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
  - `/jobs/<job_id>`
  - `/page-analysis`
  - `/api/advanced-analysis/preview`
  - `/api/advanced-analysis/analyze`

## Repository map

- `app.py`: Flask entrypoint, route definitions, JWT handling, and orchestration of extraction/loading/enrichment/analysis.
- `static/backend/`: Python backend modules and page-specific frontend scripts.
- `templates/`: Jinja/HTML pages for login, signup, account management, extractor, explorer, advanced analysis, FAQ, and landing pages.
- `static/assets/`: HTML5UP "Forty" theme assets plus project CSS/JS extracted from templates.
- `ddl/`: SQL Server table definitions for `Users`, `Comments`, and `EnrichedComments`.
- `model_fine_tuning/`: dataset preparation, download helpers, LoRA training script, synthetic slang generator, and saved adapters/artifacts.
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
- `peft`
- `datasets`
- `lingua-language-detector`
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
   - Local development defaults should remain `APP_ENV=development`, `DEBUG=true`, `JWT_COOKIE_SECURE=false`, and `JWT_COOKIE_SAMESITE=Lax` for `http://localhost` or `http://127.0.0.1`.
   - Production deployments should use `APP_ENV=production`, which defaults to `DEBUG=false` and `JWT_COOKIE_SECURE=true`. Override `JWT_COOKIE_SAMESITE` only if your deployment needs a stricter or cross-site cookie policy.
   - `CORS_ALLOWED_ORIGINS` should contain a comma-separated list of trusted frontend origins. The default local allowlist is `http://localhost:5000,http://127.0.0.1:5000`.
   - `TRUST_PROXY_HEADERS` should remain `false` unless the app is definitely behind a trusted reverse proxy that sets `X-Forwarded-For` correctly.
   - Abuse-control defaults are configurable through `RATE_LIMIT_*` variables for `/login`, `/process-data`, `/enrich-comments`, and the analysis APIs. The shipped defaults are biased toward avoiding brute-force and bot activity, with looser thresholds for login and analysis than for the heavier processing routes.
4. Create the SQL Server database and tables from:
   - `ddl/Users.sql`
   - `ddl/Comments.sql`
   - `ddl/EnrichedComments.sql`
   - The repository currently contains only these three schema files; there is no separate `ddl/migrations/` folder in the tracked tree.
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

- `/process-data` keeps extraction rows in memory only long enough to load one post batch at a time.
- `load_row_batches()` chunks oversized batches before insertion so long runs do not accumulate all rows in RAM.
- `enrich_comments()` supports scoped processing by mode, page name, page id, or delta.
- Enrichment uses chunked DB reads, batched transformer inference, temp-table staging, and separate read/write connections.
- The extractor page now polls queued jobs and prevents enrichment while extraction is still running.
- Advanced analysis supports filters for page, source, language, sentiment, likes, time windows, first-comment sentiment, and text search.

## Fine-tuning workspace

- `model_fine_tuning/train_lora_sentiment.py` trains LoRA adapters from `balanced_dataset.csv`.
- `model_fine_tuning/prepare_and_balance_data.py` now exports CSV by default; Hugging Face `save_to_disk()` artifacts are opt-in via `--save-hf-dataset`.
- The dataset download helpers under `model_fine_tuning/*/download_dataset.py` also default to CSV-only export.
- Saved `dataset_info.json`, `state.json`, and `.arrow` files are not required for the current training path.

## Current caveats

- `static/backend/extract_data.py` uses optional `.env` variables for its standalone `__main__` entrypoint.
- Generated directories such as `__pycache__/` may be present in the repository worktree.

## License

Frontend assets are based on HTML5UP "Forty" and are covered by the attribution/license text in `LICENSE.txt`.
