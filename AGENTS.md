# LedgerPilot project instructions

## Product and financial safety

- Treat financial correctness, tenant isolation, and auditability as core requirements.
- Use `Decimal` and SQL `DECIMAL`/`NUMERIC` for monetary values. Never use binary floating point for money.
- Never represent uncertain extraction, matching, or AI conclusions as verified facts.
- Keep deterministic calculations separate from AI reasoning. AI must use narrow application tools, not unrestricted database access.
- Consequential financial changes require explicit human authorization and an audit record.
- Preserve provenance for extracted data and evidence; do not invent supporting records.

## Architecture

- Keep `frontend/` (Next.js/TypeScript) and `backend/` (FastAPI/Python) separate.
- Use a modular monolith. Place backend features under `backend/app/modules/<feature>/` and keep API routing, service logic, schemas, and persistence concerns understandable for a solo developer.
- When implementing reconciliation, separate candidate generation, scoring, rules, and confirmation. Preserve individual candidates with method, factors, confidence, status, and rationale.
- When implementing AI investigation, separate tools, prompts, workflows, and evaluators; record tool executions, accessed record references, results, and timestamps. Abstract the model provider and validate structured outputs before storage.
- Enforce business-level access in backend service/query boundaries; never trust a client-provided business identifier as authorization.
- Resolve each business-scoped request against the authenticated user’s current membership in SQL Server. Do not trust JWT claims for business IDs or roles.
- Use SQL Server as the supported database. Do not substitute SQLite or claim SQLite compatibility. Keep schema changes in Alembic and SQL Server administration scripts in `database/scripts/`.
- Store uploads outside `frontend/` using generated storage keys. Validate type and size before processing; hash files per business; add database uniqueness constraints for idempotency.
- Keep extracted financial values unverified until a user explicitly confirms them. Preserve the original extracted value, source document ID, row/page location, origin, and verifier when applicable.
- Treat incomplete, ambiguous, or failed extraction as visible review/error status. Make retries idempotent and preserve the source document.
- Use only synthetic, in-memory PDFs and CSVs in tests. Never commit real uploaded documents or customer financial data.
- Keep secrets in environment variables. Commit `.env.example`, never actual secrets or real user financial documents.

## Engineering workflow

- Work in approved phases. Do not begin a later phase without user approval.
- Before major architectural changes, explain the proposal and implications.
- Implement only functionality that can be meaningfully exercised; do not ship placeholder buttons or claim unverified behavior works.
- Add focused tests for changed behavior. SQL Server integration and migration checks must clearly fail/report blocked when SQL Server is unavailable; never silently skip them.
- At each phase boundary, report changed files, implemented behavior, dependencies, commands, test results, outstanding setup, and the recommended next phase.
- Keep setup instructions current in `README.md` and dependencies minimal.
