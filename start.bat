@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "VENV=%BACKEND%\.venv\Scripts"

echo ==============================================
echo   RAG Knowledge Base v0.2.1
echo ==============================================
echo.

:: ── 1. Kill old processes ──────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":9090 " ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
:: Clear stale Qdrant lock (prevents backend from hanging on startup)
if exist "%BACKEND%\data\qdrant\.lock" del /f "%BACKEND%\data\qdrant\.lock"
echo [OK]   Ports cleared

:: ── 2. Verify venv exists ──────────────────────────────────
if not exist "%VENV%\python.exe" (
    echo [ERROR] .venv not found. Please run: python -m venv backend\.venv
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('"%VENV%\python.exe" --version 2^>^&1') do echo [OK]   python: %%i

:: ── 3. Verify node_modules ─────────────────────────────────
if not exist "%FRONTEND%\node_modules\" (
    echo [INFO]  Installing frontend dependencies...
    cd /d "%FRONTEND%" && call npm install
)

:: ── 4. Ensure .env exists ──────────────────────────────────
if not exist "%BACKEND%\.env" (
    echo [INFO]  Creating .env from .env.example...
    copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
)

:: ── 5. Sync deps (fast if already installed) ───────────────
echo.
echo [INFO]  Syncing Python dependencies...
"%VENV%\python.exe" -m pip install -r "%BACKEND%\requirements.txt" -q --disable-pip-version-check >nul 2>&1
if errorlevel 1 (
    echo [WARN]  Some packages may be missing. Continue anyway...
)
echo [OK]   Dependencies ready

:: ── 6. Create log dir ─────────────────────────────────────
if not exist "%BACKEND%\logs" mkdir "%BACKEND%\logs"

:: ── 7. Start backend ───────────────────────────────────────
echo.
echo Starting backend on http://127.0.0.1:9090 ...
start "RAG-Backend" /min /d "%BACKEND%" cmd /c ""%VENV%\pythonw.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 9090 > "%BACKEND%\logs\backend.log" 2>&1"

:: ── 8. Start frontend ──────────────────────────────────────
echo Starting frontend on http://localhost:5173 ...
start "RAG-Frontend" /min /d "%FRONTEND%" cmd /c "npm run dev"

:: ── 9. Wait and verify (bge-large model loading takes 60~90s)
echo.
echo Waiting for backend (bge-large model ~90s)...
for /l %%i in (1,1,45) do (
    timeout /t 2 >nul
    curl -s http://127.0.0.1:9090/health >nul 2>&1 && goto :ready
)
echo [WARN] Backend still loading, check: backend\logs\backend.log
:ready

:: ── 10. Open browser ────────────────────────────────────────
start "" http://localhost:5173

echo.
echo ==============================================
echo   Backend  : http://127.0.0.1:9090
echo     Docs   : http://127.0.0.1:9090/docs
echo   Frontend : http://localhost:5173
echo ==============================================
echo.
echo   Browser opened. You can close this window.
pause >nul
