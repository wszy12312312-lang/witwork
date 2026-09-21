@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM  WitWork launcher
REM  KEEP THIS FILE ASCII-ONLY AND CRLF.
REM  cmd.exe parses .bat in the OEM codepage (GBK on zh-CN).
REM  UTF-8 Chinese comments + LF-only line endings desync the
REM  parser: stray bytes split lines and fragments get executed
REM  as commands (this file was broken exactly that way).
REM ============================================================

set "PY=venv\Scripts\python.exe"

REM --- 1. first run: create venv and install dependencies ---
if not exist "%PY%" (
  echo [WitWork] Creating virtual environment, please wait...
  python -m venv venv
  if errorlevel 1 goto fail
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)

REM --- 2. start the server only if it is not already running ---
"%PY%" -c "import urllib.request,sys;urllib.request.urlopen('http://127.0.0.1:8723/api/health',timeout=2);sys.exit(0)" >nul 2>&1
if errorlevel 1 (
  echo [WitWork] Starting local server...
  start "WitWork server" "%PY%" -m server.main
)

REM --- 3. wait until healthy, then open the browser ---
"%PY%" wait_open.py
if errorlevel 1 goto fail
exit /b 0

:fail
echo.
echo [WitWork] Startup failed - see the messages above.
echo If Python 3 is missing, install it and run this again.
echo Manual start: "%PY%" -m server.main
pause
exit /b 1
