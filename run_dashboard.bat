@echo off
title DSB Command Center
echo ===================================================
echo Starting DSB Command Center Dashboard Server...
echo ===================================================
echo.

set PYTHON_PATH="C:\Users\mohdu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

REM Launch default web browser to the server URL
start "" "http://localhost:8080"

REM Run python server script
if exist %PYTHON_PATH% (
    %PYTHON_PATH% -u dashboard_server.py
) else (
    python -u dashboard_server.py
)

pause
