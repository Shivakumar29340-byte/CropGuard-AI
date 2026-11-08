# CropGuard AI

AI-based crop disease detection with blockchain farm records.

## Status
Phase 1 complete: static website (`web/`).
Phase 2 complete: Flask backend + SQLite (`backend/`), login/register connected.
AI model, blockchain and mobile app arrive in later phases.

## Run the website (Windows)
Option A: double-click `web\index.html`.

Option B (recommended): open Command Prompt in the project folder and run:

    cd web
    python -m http.server 8000

Then open http://localhost:8000 in Chrome or Edge.

The pages load Bootstrap and fonts from the internet, so connect to the internet the first time.

## Run the backend (Windows, Command Prompt)

    cd C:\Projects\CropGuard_AI\backend
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.txt
    python test_api.py
    python app.py

The API runs at http://127.0.0.1:5000 (check http://127.0.0.1:5000/api/health).
Keep this window open, then run the website in a second window (see above).
