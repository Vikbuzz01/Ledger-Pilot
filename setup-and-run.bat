@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "LEDGERPILOT_ROOT=%CD%"

where py >nul 2>&1
if errorlevel 1 (
  where python >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Python 3.11 or newer was not found. Install Python and enable the launcher or PATH entry.
    exit /b 1
  )
  set "PYTHON=python"
) else (
  set "PYTHON=py -3"
)
where node >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js was not found. Install Node.js 20.9 or newer and reopen this window.
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm was not found. Install Node.js with npm and reopen this window.
  exit /b 1
)

%PYTHON% --version
%PYTHON% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.11 or newer is required.
  exit /b 1
)
node --version
node -e "const [major,minor]=process.versions.node.split('.').map(Number);process.exit(major>20||(major===20&&minor>=9)?0:1)"
if errorlevel 1 (
  echo ERROR: Node.js 20.9 or newer is required.
  exit /b 1
)
call npm --version
echo Checking that the demo ports are available...
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul
if errorlevel 1 goto check_frontend_port
echo ERROR: Port 8000 is already in use. Stop the existing process and rerun this script.
exit /b 1
:check_frontend_port
netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul
if errorlevel 1 goto ports_available
echo ERROR: Port 3000 is already in use. Stop the existing process and rerun this script.
exit /b 1
:ports_available
if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  %PYTHON% -m venv backend\.venv
  if errorlevel 1 (echo ERROR: Python virtual environment creation failed.& exit /b 1)
)
echo Installing backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (echo ERROR: pip upgrade failed.& exit /b 1)
"backend\.venv\Scripts\python.exe" -m pip install -e "backend[dev]"
if errorlevel 1 (echo ERROR: backend dependency installation failed.& exit /b 1)

if not exist "frontend\node_modules" (
  echo Installing frontend dependencies from package-lock.json...
  pushd frontend
  call npm ci
  if errorlevel 1 (popd& echo ERROR: frontend dependency installation failed.& exit /b 1)
  popd
)

if not defined JWT_SECRET_KEY (
  for /f %%S in ('%PYTHON% -c "import secrets; print(secrets.token_urlsafe(48))"') do set "JWT_SECRET_KEY=%%S"
)
set "DATABASE_MODE=sqlite"
set "SQLITE_DATABASE_PATH=%LEDGERPILOT_ROOT%\backend\storage\ledgerpilot-demo.sqlite3"
set "DOCUMENT_STORAGE_ROOT=storage/demo-uploads"
set "AI_PROVIDER=none"
set "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000"
set "NEXT_PUBLIC_DEMO_MODE=true"

echo Creating demo data only when the demo account is absent. Existing demo data will be preserved.
start "LedgerPilot API" /D "%LEDGERPILOT_ROOT%\backend" cmd /k ".venv\Scripts\python.exe -m app.demo_seed && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo Waiting for API health...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; for($i=0;$i -lt 45;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 2; if($r.StatusCode -eq 200){$ready=$true; break}}catch{}; Start-Sleep -Seconds 1}; if(-not $ready){exit 1}"
if errorlevel 1 (
  echo ERROR: API did not become healthy. Keep the API window open and inspect its error output.
  exit /b 1
)
start "LedgerPilot Web" /D "%LEDGERPILOT_ROOT%\frontend" cmd /k "npm run dev -- --hostname 127.0.0.1"
echo Waiting for the Next.js application...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ready=$false; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/login -TimeoutSec 2; if($r.StatusCode -eq 200){$ready=$true; break}}catch{}; Start-Sleep -Seconds 1}; if(-not $ready){exit 1}"
if errorlevel 1 (
  echo ERROR: Frontend did not become ready. Keep its window open and inspect the error output.
  exit /b 1
)
echo LedgerPilot is ready. API logs are in the LedgerPilot API window; frontend logs are in the LedgerPilot Web window.
start "" "http://127.0.0.1:3000/login"
echo Demo credentials are displayed on the login page and documented in WINDOWS-DEMO.md.
echo To stop both applications, run stop-ledgerpilot.bat.
exit /b 0
