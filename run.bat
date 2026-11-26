@echo off
setlocal
echo ================================================================
echo   Simulacion de Defensa Estrategica - General P. Tardo
echo ================================================================
echo   Frontend 2D : http://127.0.0.1:8000
echo   Backend API : http://127.0.0.1:8000/docs
echo ================================================================

start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
python -m uvicorn main:app --app-dir "%~dp0backend" --reload --host 127.0.0.1 --port 8000
if errorlevel 1 pause
endlocal
