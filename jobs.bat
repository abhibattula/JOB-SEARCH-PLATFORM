@echo off
rem Run headless commands with the project's venv, e.g.:
rem   jobs refresh          jobs refresh --force          jobs load-sponsorship
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup first:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0cli.py" %*
