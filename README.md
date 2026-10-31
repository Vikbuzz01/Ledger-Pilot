# LedgerPilot

LedgerPilot helps small businesses reconcile bank activity against invoices. It turns uploaded statements and invoices into reviewable financial records, proposes deterministic matches, investigates exceptions with evidence-backed AI when configured, and requires a person to authorize financial allocations.

## Problem

Small teams often compare bank statements, invoices, partial payments, duplicate records, and unmatched transactions by hand. That is slow and hard to audit. LedgerPilot keeps source documents, extraction provenance, match candidates, investigation evidence, approvals, and resulting balances connected in one tenant-isolated workspace.

## Features

- Registration, login, profiles, businesses, memberships, and role checks.
- Private CSV/PDF upload, duplicate-file checks, extraction status, field provenance, and explicit value verification.
- Exact, partial, split, duplicate, mismatch, currency, and unmatched reconciliation results. Matches remain proposals until human review.
- Read-only investigation tools, optional structured AI findings with citations, and a clear unavailable state when no provider is configured.
- Human decisions, invoice allocation balances, and audit history.
- Native Windows SQL Server development and a standalone SQLite demo mode.

## Architecture and technology

The modular monolith keeps `frontend/` (Next.js, React, TypeScript, Tailwind CSS) separate from `backend/` (FastAPI, Pydantic, SQLAlchemy). SQL Server Express is the primary developer database, accessed through pyodbc and Microsoft ODBC Driver 18. Alembic revisions remain the SQL Server schema migration history. SQLite is an optional portable demonstration mode initialized from SQLAlchemy metadata with a version marker and fail-closed checks.

Financial amounts use Python `Decimal`. SQL Server stores them as `DECIMAL(19,4)`; SQLite stores canonical decimal text to avoid SQLite NUMERIC affinity's floating point conversion. Allocation totals are summed as `Decimal` in the application. Matching is deterministic; the AI provider cannot access unrestricted SQL or approve or allocate funds.

## SQL Server developer setup (native Windows)

Requirements: Windows, Python 3.11+, Node.js 20.9+ with npm, SQL Server Express, SSMS or `sqlcmd`, and Microsoft ODBC Driver 18. Docker is not used.

Create `.env` from the placeholder file and set a fresh secret:

```powershell
Copy-Item .env.example .env
$jwtSecret = py -3 -c "import secrets; print(secrets.token_urlsafe(48))"
(Get-Content .env) -replace '^JWT_SECRET_KEY=.*$', "JWT_SECRET_KEY=$jwtSecret" | Set-Content .env
Remove-Variable jwtSecret
```

Keep `DATABASE_MODE=sqlserver`; adjust `DATABASE_URL` for the local instance as needed. Create `LedgerPilot` in SSMS or run:

```powershell
sqlcmd -S .\SQLEXPRESS -E -C -i database/scripts/01-create-database.sql
```

Backend terminal:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
pytest -q
ruff check app tests
ruff format --check app tests
uvicorn app.main:app --reload
```

Frontend terminal:

```powershell
cd frontend
npm ci
npm run lint
npm run build
npm run dev
```

FastAPI serves at `http://127.0.0.1:8000`; health is `GET /health`, OpenAPI docs are `/docs`. Next.js serves at `http://localhost:3000`. SQL Server integration tests and Alembic checks require a reachable configured SQL Server and report failure when it is unavailable.

## Portable SQLite demo mode

Judges do not need SQL Server, SSMS, ODBC Driver 18, or Docker. Install Python 3.11+ and Node.js 20.9+ with npm, then double-click `setup-and-run.bat`. See [WINDOWS-DEMO.md](WINDOWS-DEMO.md) for startup, stop, reset, and independent start instructions.

The script uses `backend/storage/ledgerpilot-demo.sqlite3` and private generated files in repository `storage/demo-uploads/`. It initializes a new database on first run without overwriting an existing file and creates the demo account/workspace idempotently.

Demo credentials:

- Email: `demo@ledgerpilot.com`
- Password: `LedgerPilot-Demo-2026!`

Northstar Demo Studio is synthetic and contains generated source CSV/PDFs, verified examples, exact/split/partial/unmatched items, proposed candidates, and an audit event. It has no hidden expected-results data available to the AI tools. Candidates still need a human decision. AI is disabled until configured; the UI shows this status and does not generate an invented report.

SQLite schema policy: when the DB file is empty, application startup creates the full ORM schema and writes marker `20261101_0006`. On later start it verifies the marker and expected tables; unknown, partial, or older schemas fail closed. Existing SQL Server Alembic migrations include SQL Server-specific operations, so Alembic explicitly rejects SQLite mode rather than pretending to migrate it. Back up important data before any schema transition; reset script is only for disposable synthetic demo data.

## AI provider configuration and live investigation

AI is optional. Deterministic reconciliation works with no provider. To enable a compatible chat completions provider, set these variables in `.env`:

```dotenv
AI_PROVIDER=openai_compatible
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=replace-with-your-own-secret
AI_MODEL=gpt-4o-mini
```

Keep the real key out of Git. Restart FastAPI. In the application, open a reconciliation exception and start an investigation. Confirm the investigation report cites IDs visible in its recorded tool history, that hypotheses remain separate from verified facts, and that insufficient evidence or failed provider output does not produce a completed report. A person must separately review a recommendation. **No live provider call was performed for this repository verification**; automated tests use a mock provider and the no-key unavailable state.

## API areas

API routes are under `/api/v1`; interactive documentation is at `/docs` while the backend is running.

- Identity: `/auth/register`, `/auth/login`, `/users/me`.
- Businesses: `/businesses`, `/businesses/{business_id}`, and `/members` routes.
- Documents: business `/documents` upload/list and document detail, file, retry, invoice verification, and transaction verification routes.
- Reconciliation: `/reconciliation/runs`, run candidates/exceptions, candidate decisions, invoice balances, aliases, audit, and exception resolution.
- Investigation: exception `/investigations`, investigation details/tool history, and recommendation decisions.

All business operations re-check current membership in the database. Uploads are stored outside the frontend. Download paths are generated and tenant checked. Reconciliation considers only records whose required fields were explicitly verified.

## Verification and synthetic testing

Automated tests use generated CSV/PDF inputs and keep expected outcomes in test assertions, separate from application data. Coverage includes exact/partial/split proposals, duplicate records, mismatches, unmatched transactions, provider unavailable/mock provider, tenant isolation, allocation overrun prevention, idempotency, and review/audit history. The full SQL Server suite still needs a reachable SQL Server Express connection. SQLite API regression coverage can run with:

```powershell
cd backend
$env:DATABASE_MODE = "sqlite"
$env:SQLITE_DATABASE_PATH = "storage/test-ledgerpilot.sqlite3"
$env:JWT_SECRET_KEY = "use-a-random-secret-with-at-least-32-characters"
python -m pytest tests/test_sqlite_demo.py tests/test_identity_and_tenancy.py tests/test_reconciliation.py -q -p no:tmpdir
```

`test_database.py` verifies SQL Server connectivity and Alembic head; it is intentionally not an SQLite test.

## Security, limitations, and local data

- `.env`, SQLite database/journal files, private uploads, SQL Server data files, logs, and generated test artifacts are ignored by Git. `.env.example` contains placeholders only.
- Authentication uses password hashing and short-lived JWT access tokens. Tokens are held in per-tab session storage by the frontend.
- AI has read-only, scoped tools; no arbitrary SQL or consequential actions are exposed. Reports are schema/evidence validated and require a human decision.
- Scanned PDFs do not have OCR configured. Text PDF extraction uses heuristics and always requires user verification.
- Split-payment candidate groups are limited to 2–4 transactions. Larger or ambiguous groups need manual review.
- SQLite is a standalone demo option, not the primary production database or a substitute for the SQL Server migration/test path. It uses a single local file and is not a multi-user production deployment recommendation.
- No public hosted deployment is configured by default. For a production deployment, provision managed SQL Server and ODBC Driver 18, set `DATABASE_MODE=sqlserver`, `DATABASE_URL`, a unique 32+ character `JWT_SECRET_KEY`, `DOCUMENT_STORAGE_ROOT` on private persistent storage, and `CORS_ALLOWED_ORIGINS` to the exact frontend origin(s). Apply `alembic upgrade head` from `backend/`. Build the frontend with `NEXT_PUBLIC_API_URL` set to the public HTTPS API URL, then run `npm run start`. Run FastAPI behind a TLS-terminating reverse proxy or service manager (for example, `uvicorn app.main:app --host 127.0.0.1 --port 8000` behind the proxy); keep SQL Server and document storage private, configure backups/retention, and do not use SQLite for multi-user production. Never expose the API key or JWT secret to the frontend.

## Submission checklist

### GitHub repository

- [ ] Review `git status` and staged files; do not add `.env`, SQLite files, private uploads, or customer data.
- [ ] Rotate any credential that was ever exposed; use environment-based secrets only.
- [ ] Include setup instructions, synthetic-only demo account details, and known limitations.
- [ ] Run the backend checks and frontend `npm run lint`, `npm run build`, and `npm audit`.

### Hackathon submission

- [ ] Verify the Windows demo on a clean machine/user profile.
- [ ] Include repository URL, problem statement, features, architecture, and setup instructions.
- [ ] State truthfully that live AI is optional and has not been live-verified unless you perform that call.
- [ ] Record a four-minute walkthrough using the outline below.

### Four-minute demo video

1. **0:00–0:30 — Problem:** show the manual bank/invoice reconciliation burden and introduce LedgerPilot.
2. **0:30–1:10 — Workspace:** sign in with the demo account and show the synthetic business dashboard and totals.
3. **1:10–2:00 — Source records:** open uploaded bank CSV/PDF records and show source page/row provenance and verification state.
4. **2:00–2:50 — Reconciliation:** show exact, split, partial, and unmatched examples; point out that candidates are proposals.
5. **2:50–3:30 — Investigation:** open an exception, show available evidence/tool history and the AI-unavailable state (or a real, cited investigation if live AI was tested).
6. **3:30–4:00 — Human control:** approve one reviewed candidate, show the updated invoice balance and audit event, then close with tenant and evidence protections.

## Repository layout

- `backend/app/modules/`: identity, business tenancy, documents, financial records, reconciliation, matching, investigation, and approval logic.
- `backend/alembic/`: SQL Server migrations.
- `backend/tests/`: synthetic API/database behavior tests.
- `frontend/`: Next.js application.
- `database/scripts/`: SQL Server administration scripts.
- `setup-and-run.bat`, `stop-ledgerpilot.bat`, `reset-demo-data.bat`: local Windows demo controls.
