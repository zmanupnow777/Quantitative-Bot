@echo off
REM One-click launcher for the trading dashboard.
REM Double-click this file (or make a desktop shortcut to it) to open the dashboard.
cd /d "%~dp0"
echo Starting the trading dashboard...
echo It will open in your browser at http://localhost:8501
echo Close this window to stop the dashboard.
".venv\Scripts\python.exe" -m streamlit run bot\dashboard.py
pause
