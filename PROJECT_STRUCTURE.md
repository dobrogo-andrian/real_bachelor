# Project Structure

This document reflects the current repository layout and the responsibilities of each major part of the project.

## High-level architecture

- `app.py` is the Flask entrypoint and the orchestration layer.
- `templates/` contains the rendered HTML pages.
- `static/assets/` contains the base frontend theme and styling assets.
- `static/backend/` contains the Python data pipeline plus auth/page support scripts.
- `ddl/` contains SQL Server schema files.
- `model_fine_tuning/` contains fine-tuning and dataset-preparation scripts.

## Top-level tree

```text
real_bachelor/
|-- .idea/
|-- app.py
|-- README.md
|-- PROJECT_STRUCTURE.md
|-- TODO.md
|-- LICENSE.txt
|-- requirements.txt
|-- ddl/
|   |-- Comments.sql
|   |-- EnrichedComments.sql
|   |-- migrations/
|   |-- Users_AddInstagramCookies.sql
|   `-- Users.sql
|-- model_fine_tuning/
|   |-- common.py
|   |-- prepare_and_balance_data.py
|   |-- train_lora_sentiment.py
|   |-- balanced_sentiment_dataset/
|   |-- sentiment_lora_adapters/
|   |-- Sp1786-multiclass-sentiment-analysis-dataset/
|   |-- ukr-detect-ukr-emotions-binary/
|   `-- symbols/
|-- static/
|   |-- assets/
|   |   |-- css/
|   |   |   |-- advanced-analysis-page.css
|   |   |   |-- explorer-page.css
|   |   |   |-- extractor.css
|   |   |   |-- login.css
|   |   |   `-- signup.css
|   |   |-- images/
|   |   |-- js/
|   |   |   |-- advanced-analysis-page.js
|   |   |   |-- explorer-page.js
|   |   |   `-- extractor.js
|   |   |-- sass/
|   |   `-- webfonts/
|   `-- backend/
|       |-- common_utils.py
|       |-- db_connection.py
|       |-- enrich_comments.py
|       |-- explorer_analysis.py
|       |-- extract_data.py
|       |-- faq_content.py
|       |-- job_queue.py
|       |-- load_to_db.py
|       |-- auth/
|       |   |-- account.js
|       |   |-- faq.js
|       |   |-- home.js
|       |   |-- login.js
|       |   |-- menu_auth.js
|       |   `-- signup.js
|       `-- __pycache__/
|-- templates/
|   |-- advanced_analysis.html
|   |-- account.html
|   |-- elements.html
|   |-- explorer.html
|   |-- extractor.html
|   |-- faq.html
|   |-- index.html
|   |-- login.html
|   |-- signup.html
|   `-- test.html
`-- __pycache__/
```

## Core backend files

### `app.py`

Responsibilities:

- configures Flask, CORS, and JWT cookie authentication
- serves public and protected HTML pages
- exposes API endpoints for extraction, enrichment, and analysis
- coordinates `extract_data`, `load_to_db`, `enrich_comments`, job polling, and explorer analysis helpers

Main route groups:

- public pages: `/`, `/login`, `/signup`, `/test`
- authenticated pages: `/extractor`, `/explorer`, `/advanced-analysis`, `/faq`, `/elements`, `/account`
- data APIs:
  - `/process-data`
  - `/enrich-comments`
  - `/jobs/<job_id>`
  - `/page-analysis`
  - `/api/advanced-analysis/preview`
  - `/api/advanced-analysis/analyze`

### `static/backend/extract_data.py`

Responsibilities:

- launches Selenium with a configured ChromeDriver
- restores a stored Instagram session or waits for manual browser login
- loads posts from a target page
- opens comment sections, scrolls, and extracts comment text plus likes
- prepares one in-memory row batch per post for immediate loading through a callback

Important details:

- per-user Instagram session cookies are stored in the `Users` table as encrypted, signed JSON payloads
- extraction aborts when Instagram presents an account restriction or challenge page
- the manual `__main__` block resolves Instagram credentials for the selected app user

### `static/backend/load_to_db.py`

Responsibilities:

- accepts prepared row batches for direct SQL loading
- still supports explicit CSV imports when a caller provides an input folder
- validates required input columns
- derives stable comment hashes
- prepares comment rows for SQL Server
- stages and merges data into `[dbo].[Comments]`

Important details:

- `dry_run=True` is supported for non-writing checks
- large row sets are chunked and staged through temp tables on SQL Server

### `static/backend/enrich_comments.py`

Responsibilities:

- fetches raw rows from `Comments`
- streams rows in batches rather than materializing the full source set
- normalizes text and datetimes
- detects dominant language
- loads and caches the merged LoRA sentiment model
- assigns sentiment labels with batch inference
- clears or refreshes scoped enrichment targets
- upserts rows into `EnrichedComments` through a staging table

Supported enrichment scope:

- whole database
- selected page name
- selected page id
- delta-only insert of comments not yet present in `EnrichedComments`

Important details:

- uses separate read and write DB connections during chunked enrichment to avoid ODBC function-sequence errors
- loads the sentiment model lazily only after the first non-empty batch is discovered

### `static/backend/explorer_analysis.py`

Responsibilities:

- converts enriched comment rows into chart-ready summaries
- builds language, sentiment, length, timing, and post-level breakdowns
- powers both explorer and advanced-analysis responses

Primary entry points:

- `build_page_analysis(selection_type, selection_value)`
- `build_analysis_from_rows(rows, ...)`

### `static/backend/db_connection.py`

Responsibilities:

- connects to SQL Server through `pyodbc`
- encrypts and decrypts Instagram credentials and stored Instagram cookie payloads with Windows DPAPI
- inserts users
- fetches login, Instagram credential, and Instagram cookie data
- builds distinct filter dimensions for explorer pages
- assembles filtered preview and analysis query results from `EnrichedComments`

Important details:

- assumes SQL Server is available on `localhost`
- connection settings are provided through environment variables loaded at app startup

### `static/backend/job_queue.py`

Responsibilities:

- provides the in-process background job queue used by `/process-data` and `/enrich-comments`
- stores job status, timestamps, payloads, and error text for `/jobs/<job_id>`

Important details:

- jobs are process-local and not durable across restarts

### `static/backend/common_utils.py`

Responsibilities:

- shared helper utilities used across the backend modules

## Frontend files

### `templates/`

- `account.html`: authenticated account management page
- `index.html`: public landing page
- `login.html`: authentication page
- `signup.html`: user creation page
- `extractor.html`: extraction workflow page
- `explorer.html`: page-level exploration UI
- `advanced_analysis.html`: filter-heavy analysis workspace
- `faq.html`: in-app product and technical reference page
- `elements.html`: theme reference page retained from the base template
- `test.html`: development/testing page

### `static/backend/auth/`

These scripts support page-level frontend behavior such as:

- account profile management
- login handling
- signup submission
- landing page auth-aware behavior
- FAQ page behavior
- shared menu/session behavior for authenticated pages

The folder name is historical; it now contains more than authentication-only logic.

### `static/assets/`

Theme and UI assets derived from HTML5UP "Forty":

- `css/`: compiled stylesheets plus project-specific page styles
- `js/`: theme JavaScript plus extracted page scripts such as `extractor.js`, `explorer-page.js`, and `advanced-analysis-page.js`
- `images/`: theme images
- `sass/`: source styles
- `webfonts/`: bundled icon fonts

### `model_fine_tuning/`

Responsibilities:

- downloads or normalizes sentiment datasets
- prepares balanced training CSVs
- trains LoRA adapters for the sentiment model
- stores generated adapters, checkpoints, and helper datasets

Important details:

- CSV is the default dataset export format; Hugging Face Arrow disk exports are opt-in
- `symbols/generation.py` is now a CLI-style generator and no longer writes files on import

## Database schema files

### `ddl/Users.sql`

Defines the `Users` table with:

- `UserID`
- `Username`
- `PasswordHash`
- `Email`
- `InstagramLoginEncrypted`
- `InstagramPasswordEncrypted`
- `InstagramCookiesEncrypted`
- `InstagramCookiesSignature`
- `InstagramCookiesUpdatedAt`

### `ddl/Comments.sql`

Defines the raw ingestion table with:

- `CommentHash` primary key
- page metadata
- post time
- comment text
- comment time
- likes
- load/update timestamps
- source tracking

### `ddl/EnrichedComments.sql`

Defines the processed analysis table with:

- the original comment identity fields
- `MainLanguage`
- `NormalizedComment`
- `Sentiment`
- processing timestamps
- source tracking

It also includes:

- a foreign key back to `Comments`
- language and sentiment check constraints
- nonclustered indexes for common filter fields

## Generated and runtime data

### `__pycache__/`

- generated Python bytecode caches
- should be treated as runtime artifacts, not source

## Current project state notes

- The repository also contains IDE metadata under `.idea/`.
- The repository worktree includes generated files such as `__pycache__/`.
- The repository includes generated training artifacts under `model_fine_tuning/sentiment_lora_adapters/`.
