@echo off
rem Start the Job Engine using the project's virtual environment.
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup first:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0app.py" %*
