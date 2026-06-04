@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "BACKEND=%ROOT%\backend"

echo ==============================================
echo   RAG Evaluation Test
echo ==============================================
echo.

:: ── 1. Stop backend ──────────────────────────────────
echo [1/4] Stopping backend...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":9090 " ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
echo [OK] Backend stopped

:: ── 2. Clear Qdrant lock ────────────────────────────
if exist "%BACKEND%\data\qdrant\.lock" del /f "%BACKEND%\data\qdrant\.lock" >nul 2>&1

:: ── 3. Run evaluation ────────────────────────────────
echo [2/4] Running evaluation...
cd /d "%BACKEND%"
call .venv\Scripts\python.exe -m eval.evaluate --kb-name default
set EVAL_EXIT=%ERRORLEVEL%
echo.
echo [3/4] Evaluation complete (exit code: %EVAL_EXIT%)

:: ── 4. Restart backend ───────────────────────────────
echo [4/4] Restarting backend...
start "RAG-Backend" /min cmd /c "cd /d "%BACKEND%" && .venv\Scripts\pythonw.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9090 > "%BACKEND%\logs\backend.log" 2>&1"

echo ==============================================
echo   Done. Backend starting on :9090
echo ==============================================
echo.
endlocal
exit /b %EVAL_EXIT%
