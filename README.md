# Real Bachelor Project

Flask-based web app with an HTML frontend and a data pipeline that scrapes Instagram comments, cleans and labels them by language, runs sentiment analysis, aggregates results, and produces visualizations.

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
3. Ensure ChromeDriver is installed and update the path in `static/backend/load_data.py`.
4. Configure your database and update connection details in `static/backend/db_connection.py`.
5. Set `JWT_SECRET_KEY` in `app.py` or via environment variable.

## Run the Web App
```bash
python app.py
```
App will start on `http://localhost:5000`.

## Data Pipeline Flow
1. Scrape comments: `static/backend/load_data.py`
2. Filter and label language: `static/backend/process_data.py`
3. Sentiment analysis: `static/backend/analyze_data.py`
4. Aggregate dataset: `static/backend/agregate_data.py`
5. Visualize: `static/backend/visualize_data.py`

## Known Risks / TODO Highlights
- JWT secret key is hardcoded.
- CSRF protection is disabled.
- `load_data.py` contains hardcoded Instagram credentials and runs on import.
- `static/backend/db_connection.py` has an incomplete `insert_data_to_database`.

See `TODO.md` for the full list.

## License
The frontend template and assets are based on HTML5UP "Forty" and are provided under CC BY 3.0. See `LICENSE.txt` for the full license text and attribution.

No explicit license has been chosen yet for the original Python/Flask code. If you want to open-source this repository, pick a license and update the repository accordingly.
