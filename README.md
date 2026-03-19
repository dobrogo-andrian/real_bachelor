# Real Bachelor Project

Flask-based web app with an HTML frontend and a data pipeline that scrapes Instagram comments, enriches them with language and sentiment metadata, stores the results in SQL Server, and exposes explorer and advanced-analysis views.

## Stack
- Backend: Flask, Flask-JWT-Extended, Flask-CORS
- Data pipeline: Selenium, pandas, langdetect, transformers
- Visualization: seaborn, matplotlib, statsmodels
- DB: SQL Server via pyodbc

## Project Structure
See `PROJECT_STRUCTURE.md` for a detailed map of modules and responsibilities.

## Setup (Local)
1. Create and activate a Python virtual environment.
2. Install dependencies (example list):
   - `flask`, `flask-cors`, `flask-jwt-extended`
   - `pyodbc`
   - `selenium`, `fake-useragent`
   - `pandas`, `langdetect`, `transformers`
   - `seaborn`, `matplotlib`, `statsmodels`
3. Ensure ChromeDriver is installed and update the path in `static/backend/extract_data.py`.
4. Configure your database and update connection details in `static/backend/db_connection.py`.
5. Set `JWT_SECRET_KEY` in `app.py` or via environment variable.

## Run the Web App
```bash
python app.py
```
App will start on `http://localhost:5000`.

## Data Pipeline Flow
1. Scrape comments: `static/backend/extract_data.py`
2. Load raw comments into SQL Server: `static/backend/load_to_db.py`
3. Enrich comments with language and sentiment: `static/backend/enrich_comments.py`
4. Build analysis structures: `static/backend/explorer_analysis.py`
5. Explore and analyze through the Flask explorer and advanced-analysis pages

## Known Risks / TODO Highlights
- JWT secret key is hardcoded.
- CSRF protection is disabled.
- `extract_data.py` contains hardcoded Instagram credentials and runs on import.
- `static/backend/db_connection.py` has an incomplete `insert_data_to_database`.

See `TODO.md` for the full list.

## License
The frontend template and assets are based on HTML5UP "Forty" and are provided under CC BY 3.0. See `LICENSE.txt` for the full license text and attribution.

No explicit license has been chosen yet for the original Python/Flask code. If you want to open-source this repository, pick a license and update the repository accordingly.
