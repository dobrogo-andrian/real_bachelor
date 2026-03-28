# TODO

## Security and Auth
- [ ] Move `JWT_SECRET_KEY` to environment variable and document setup.
- [ ] Enable CSRF protection for JWT cookies and handle CSRF tokens in frontend.

## Backend and Data Pipeline
- [ ] Remove side effects on import in `static/backend/extract_data.py` (guard with `if __name__ == "__main__":`).
- [ ] Add input validation and error handling in `/process-data`.

## Dev Experience
- [ ] Add basic tests for auth flows and data pipeline utilities.
- [ ] Add `.env` support and sample `.env.example`.

