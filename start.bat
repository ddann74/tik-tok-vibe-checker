@echo off
REM One-click startup: activates the venv (if present) and starts the server.
REM Run this from the project root: start.bat
REM
REM First-time setup still needs to happen once before this works:
REM   python -m venv venv
REM   venv\Scripts\activate
REM   pip install -r requirements.txt

if not exist venv\Scripts\activate.bat (
    echo No virtual environment found at .\venv
    echo Run this first, one line at a time:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    exit /b 1
)

call venv\Scripts\activate.bat
echo Starting NPL NSW Intelligence Engine on http://127.0.0.1:8000/ui/
uvicorn npl_engine.server:app --reload
