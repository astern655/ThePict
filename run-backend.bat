@echo off
rem Backend server (http://localhost:8000). Needs python on PATH.
cd /d "%~dp0backend"
python -m uvicorn main:app --port 8000
