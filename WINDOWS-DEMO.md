# Portable Windows demo

This standalone demo uses a local SQLite file and does not need SQL Server, SSMS, ODBC Driver 18, or Docker. It requires Python 3.11+ and Node.js 20.9+ with npm. No administrator privileges are needed.

## Start

Double-click `setup-and-run.bat`, or run it from PowerShell:

```powershell
.\setup-and-run.bat
```

The script creates `backend/.venv` if needed, installs Python dependencies, runs `npm ci` when `frontend/node_modules` is absent, seeds synthetic data only when the demo account does not already exist, starts FastAPI and Next.js in visible console windows, checks both health URLs, and opens the browser. Startup never overwrites an existing SQLite database. API logs remain visible in the API window.

Login:

- Email: `demo@ledgerpilot.com`
- Password: `LedgerPilot-Demo-2026!`

The preloaded Northstar Demo Studio business contains generated synthetic CSV/PDF documents, verified example records, exact/split/partial/unmatched reconciliation examples, and an audit trail. Candidates remain proposed until a person reviews them. Live AI is disabled by default; investigation reports are not fabricated and the UI reports AI unavailable.

## Stop and reset

Run `stop-ledgerpilot.bat` to close the visible application process trees. Run `reset-demo-data.bat` to remove the local demo SQLite file and only the generated files under repository `storage/demo-uploads`. The reset script asks for explicit confirmation. Do not reset while you need to preserve demo work.

The SQLite file is `backend/storage/ledgerpilot-demo.sqlite3`. It is local-only and ignored by Git. Schema initialization enables foreign keys, writes an application schema marker, and refuses unknown or older files; it does not run the SQL Server Alembic history. Use the SQL Server developer setup for Alembic migrations.

## Manual application commands

From the repository root, configure environment values in the current PowerShell session and start the API:

```powershell
$env:DATABASE_MODE = "sqlite"
$env:SQLITE_DATABASE_PATH = (Join-Path (Get-Location) "backend/storage/ledgerpilot-demo.sqlite3")
$env:DOCUMENT_STORAGE_ROOT = "storage/demo-uploads"
$env:JWT_SECRET_KEY = (py -3 -c "import secrets; print(secrets.token_urlsafe(48))")
cd backend
.\.venv\Scripts\python.exe -m app.demo_seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000"
$env:NEXT_PUBLIC_DEMO_MODE = "true"
cd frontend
npm run dev -- --hostname 127.0.0.1
```

Open `http://127.0.0.1:3000/login`. The demo seed refuses to run when `DATABASE_MODE` is not `sqlite` and is idempotent for the demo account.
