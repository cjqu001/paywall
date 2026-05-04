@echo off
title Paywall Bypass Launcher
color 0A

echo ============================================================
echo             PAYWALL BYPASS - LAUNCHER
echo ============================================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found. Please install Python from https://python.org
        echo         Make sure to check "Add Python to PATH" during install.
        pause
        exit /b 1
    )
    set PYTHON=py
) else (
    set PYTHON=python
)

echo [OK] Python found.
echo.

:: Move to script directory so relative paths work
cd /d "%~dp0"

:: Install requirements if needed
echo [*] Installing/verifying required packages...
%PYTHON% -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install packages. Check your internet connection.
    pause
    exit /b 1
)
echo [OK] Packages ready.
echo.

:: Brief pause then open browser
echo [*] Starting server at http://127.0.0.1:5000 ...
echo.
echo ============================================================
echo   HOW TO USE
echo ============================================================
echo.
echo   1. A browser window will open automatically.
echo.
echo   2. Paste any paywalled article URL into the input box.
echo      Example: https://www.wsj.com/articles/some-article
echo.
echo   3. Hit Submit. The full article will load in your browser.
echo.
echo   4. For Wall Street Journal specifically:
echo      - Go to wsj.com and find the article you want
echo      - Copy the full URL from your address bar
echo      - Paste it into the box and submit
echo.
echo   5. To stop the server, close this window.
echo.
echo ============================================================
echo.

:: Wait 2 seconds then open browser
ping -n 3 127.0.0.1 >nul 2>&1
start "" "http://127.0.0.1:5000"

:: Launch the server (this stays open)
cd app
%PYTHON% portable.py

echo.
echo [*] Server stopped. Press any key to close.
pause >nul
