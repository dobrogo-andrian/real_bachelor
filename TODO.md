# TODO

## Security and Auth
- [ ] Move `JWT_SECRET_KEY` to environment variable and document setup.
- [ ] Enable CSRF protection for JWT cookies and handle CSRF tokens in frontend.
- [ ] Remove hardcoded Instagram credentials from `static/backend/extract_data.py`.

## Backend and Data Pipeline
- [ ] Remove side effects on import in `static/backend/extract_data.py` (guard with `if __name__ == "__main__":`).
- [ ] Fix `insert_data_to_database` in `static/backend/db_connection.py` (undefined vars, duplicate logic).
- [ ] Add input validation and error handling in `/process-data`.
- [ ] Define and document output directories (`language_marked_comments`, `sentiment_analysis`, `final_dataset`).

## Dev Experience
- [ ] Add `requirements.txt` or `pyproject.toml` with pinned dependencies.
- [ ] Add basic tests for auth flows and data pipeline utilities.
- [ ] Add `.env` support and sample `.env.example`.

## Docs
- [ ] Expand `README.md` with step-by-step setup and data pipeline usage.
- [ ] Document database schema and required tables.
