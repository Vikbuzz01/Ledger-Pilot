# LedgerPilot

LedgerPilot is a financial reconciliation platform for small businesses. It uses a modular monolith with a separate Next.js frontend and FastAPI backend. The approved identity/business tenancy and financial document ingestion stages are implemented on SQL Server.

## Native Windows requirements

- Windows 10/11 or Windows Server supported by your SQL Server release.
- Python 3.11 or newer.
- Node.js 20.9 or newer with npm.
- A locally installed Microsoft SQL Server instance and SSMS or `sqlcmd` for administration.
- Microsoft ODBC Driver 18 for SQL Server installed on Windows.

Docker and Docker Compose are not used or required.

## Configure SQL Server

This project uses Windows integrated authentication for local development. The `.env.example` connection targets the local SQLEXPRESS named instance. If SQL Server Browser or named-instance discovery is unavailable, configure a static TCP port for SQLEXPRESS and use `localhost:<port>` in `DATABASE_URL` instead.

Create the development database from a PowerShell session with Windows credentials that have permission to create databases:

```powershell
sqlcmd -S .\SQLEXPRESS -E -C -i database/scripts/01-create-database.sql
```

Alternatively, create a database named `LedgerPilot` in SSMS. The application connects using the Windows identity running the backend process; grant that identity access to the database as needed. ODBC Driver 18 encrypts connections by default; the local sample URL trusts the instance certificate for development. Use a properly trusted certificate in production.

## Backend setup and run

From the repository root, create `.env` from the example, set a unique JWT signing key, and adjust `DATABASE_URL` if your SQL Server uses a different instance name or port. Do not commit `.env`.

```powershell
Copy-Item .env.example .env
$jwtSecret = py -3 -c "import secrets; print(secrets.token_urlsafe(48))"
(Get-Content .env) -replace '^JWT_SECRET_KEY=.*$', "JWT_SECRET_KEY=$jwtSecret" | Set-Content .env
Remove-Variable jwtSecret
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
pytest -q
uvicorn app.main:app --reload
```

The API runs independently at `http://localhost:8000`; its process health endpoint is `GET /health`. Database tests require SQL Server and deliberately fail if configuration, connectivity, or migration verification is unavailable. This application supports SQL Server; it is not SQLite-compatible.

Implemented API areas:

- Identity: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET/PATCH /api/v1/users/me`, and `PUT /api/v1/users/me/password`.
- Businesses: `GET/POST /api/v1/businesses`, `GET/PATCH /api/v1/businesses/{business_id}`, and business member list/add/role/remove endpoints under `/members`.
- Documents: upload and list under `/api/v1/businesses/{business_id}/documents`; read extracted previews, open the protected source, retry failed extraction, and verify invoice/transaction fields under the document route.

Access tokens are short-lived bearer JWTs. The browser keeps them in session storage for the current tab. Every business route rechecks SQL Server membership and role. Document files default to the ignored `storage/uploads/` folder, outside the frontend; set `DOCUMENT_STORAGE_ROOT` and `MAX_DOCUMENT_UPLOAD_MB` in `.env` to configure storage and the upload limit. Duplicate file hashes are unique per business, while transaction source row constraints make processing retries idempotent.

## Frontend setup and run

In another PowerShell terminal, from the repository root:

```powershell
cd frontend
npm install
npm run build
npm run lint
npm run dev
```

The Next.js app runs independently at `http://localhost:3000`. It reads `NEXT_PUBLIC_API_URL` from the environment and defaults to `http://localhost:8000`. It provides registration, login, business creation/selection, and a document upload/review workspace. Extracted values remain marked for review until explicitly verified.

## Repository layout

- `backend/app/`: FastAPI application, settings, SQLAlchemy base and session management.
- `backend/alembic/`: SQL Server migrations.
- `backend/tests/`: API checks and explicit database connectivity/migration verification.
- `frontend/`: Next.js App Router application.
- `database/scripts/`: version-controlled SQL Server administration scripts.

The approved identity/business and document-ingestion stages are implemented. OCR for scanned PDFs is not configured; such PDFs are retained with a visible manual-review status. Reconciliation and AI investigation are not implemented.
