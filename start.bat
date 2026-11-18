@echo off
cd /d "%~dp0backend"
start "" cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:8000/app/"
"..\venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000
pause