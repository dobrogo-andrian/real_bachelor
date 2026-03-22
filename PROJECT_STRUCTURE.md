# Project Structure

This document reflects the current repository layout and the responsibilities of each major part of the project.

## High-level architecture

- `app.py` is the Flask entrypoint and the orchestration layer.
- `templates/` contains the rendered HTML pages.
- `static/assets/` contains the base frontend theme and styling assets.
- `static/backend/` contains the Python data pipeline plus some page-specific JavaScript.
- `ddl/` contains SQL Server schema files.
- `unprocessed_data/` and `cookie/` store generated runtime artifacts.

## Top-level tree

```text
real_bachelor/
|-- app.py
|-- README.md
|-- PROJECT_STRUCTURE.md
|-- TODO.md
|-- LICENSE.txt
|-- requirements.txt
|-- cookie/
|   `-- cookies.pkl
|-- ddl/
|   |-- Comments.sql
|   |-- EnrichedComments.sql
|   `-- Users.sql
|-- static/
|   |-- assets/
|   |   |-- css/
|   |   |-- images/
|   |   |-- js/
|   |   |-- sass/
|   |   `-- webfonts/
|   `-- backend/
|       |-- common_utils.py
|       |-- db_connection.py
|       |-- enrich_comments.py
|       |-- explorer_analysis.py
|       |-- extract_data.py
|       |-- load_to_db.py
|       |-- auth/
|       |   |-- auth.js
|       |   |-- faq.js
|       |   |-- home.js
|       |   |-- login.js
|       |   `-- signup.js
|       |-- old_apprach/
|       `-- __pycache__/
|-- templates/
|   |-- advanced_analysis.html
|   |-- elements.html
|   |-- explorer.html
|   |-- extractor.html
|   |-- faq.html
|   |-- index.html
|   |-- login.html
|   |-- signup.html
|   `-- test.html
|-- unprocessed_data/
|   `-- comments1/
|       `-- lpnu_official_1.csv
`-- __pycache__/
```

## Core backend files

### `app.py`

Responsibilities:

- configures Flask, CORS, and JWT cookie authentication
- serves public and protected HTML pages
- exposes API endpoints for extraction, enrichment, and analysis
- coordinates `extract_data`, `load_to_db`, `enrich_comments`, and explorer analysis helpers

Main route groups:

- public pages: `/`, `/login`, `/signup`, `/test`
- authenticated pages: `/extractor`, `/explorer`, `/advanced-analysis`, `/faq`, `/elements`
- data APIs:
  - `/process-data`
  - `/enrich-comments`
  - `/page-analysis`
  - `/api/advanced-analysis/preview`
  - `/api/advanced-analysis/analyze`

### `static/backend/extract_data.py`

Responsibilities:

- launches Selenium with a configured ChromeDriver
- logs into Instagram
- loads posts from a target page
- opens comment sections, scrolls, and extracts comment text plus likes
- writes CSV files for downstream loading

Important details:

- runtime output is written under `unprocessed_data/`
- cookie persistence is stored in `cookie/cookies.pkl`
- a manual `__main__` block still contains hardcoded Instagram credentials

### `static/backend/load_to_db.py`

Responsibilities:

- walks `unprocessed_data/` recursively for CSV files
- validates required input columns
- derives stable comment hashes
- prepares comment rows for SQL Server
- merges data into `[dbo].[Comments]`

Important details:

- default input folder is the repository-level `unprocessed_data/`
- `dry_run=True` is supported for non-writing checks

### `static/backend/enrich_comments.py`

Responsibilities:

- fetches raw rows from `Comments`
- normalizes text and datetimes
- detects dominant language
- filters text for language-specific processing
- loads transformer models
- assigns sentiment labels
- clears or refreshes scoped enrichment targets
- upserts rows into `EnrichedComments`

Supported enrichment scope:

- whole database
- selected page name
- selected page id

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
- encrypts and decrypts Instagram credentials with Windows DPAPI
- inserts users
- fetches login and Instagram credential data
- builds distinct filter dimensions for explorer pages
- assembles filtered preview and analysis query results from `EnrichedComments`

Important details:

- assumes SQL Server is available on `localhost`
- currently uses hardcoded DB credentials in source

### `static/backend/common_utils.py`

Responsibilities:

- shared helper utilities used across the backend modules

## Frontend files

### `templates/`

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

- login handling
- signup submission
- landing page auth-aware behavior
- FAQ page behavior

The folder name is historical; it now contains more than authentication-only logic.

### `static/assets/`

Theme and UI assets derived from HTML5UP "Forty":

- `css/`: compiled stylesheets plus project-specific overrides
- `js/`: theme JavaScript
- `images/`: theme images
- `sass/`: source styles
- `webfonts/`: bundled icon fonts

## Database schema files

### `ddl/Users.sql`

Defines the `Users` table with:

- `UserID`
- `Username`
- `PasswordHash`
- `Email`
- `InstagramLoginEncrypted`
- `InstagramPasswordEncrypted`

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
- `FilteredComment`
- `Sentiment`
- processing timestamps
- source tracking

It also includes:

- a foreign key back to `Comments`
- language and sentiment check constraints
- nonclustered indexes for common filter fields

## Generated and runtime data

### `unprocessed_data/`

- stores raw CSV files produced by the scraper
- current sample content: `comments1/lpnu_official_1.csv`

### `cookie/`

- stores Selenium cookie state in `cookies.pkl`

### `__pycache__/`

- generated Python bytecode caches
- should be treated as runtime artifacts, not source

## Current project state notes

- `static/backend/old_apprach/` exists but is currently empty.
- The repository worktree includes generated files such as `__pycache__/` and extraction output.
- Authentication and database configuration are functional for local development but still rely on hardcoded secrets/settings in source files.
