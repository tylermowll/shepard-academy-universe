# Backend instructions

Follow root AGENTS.md and the current task. Add modules and migrations only when
they have working behavior; the target entity diagram is not a task to scaffold
every future table.

- Keep exact mathematics and immutable domain objects independent of FastAPI,
  database models, and provider clients. Never evaluate learner text as code.
- Public Pydantic schemas must be separate from private persistence/domain objects.
  Prove with serialization tests that expected answers and secrets cannot leak.
- SQLite is the supported database (D004). Use SQLAlchemy/Alembic with Python's
  sqlite3 driver. Test migrations and transactional invariants against temporary
  on-disk databases with the production connection settings, not mocked SQL or
  in-memory-only fixtures. Check the library version loaded by Python.
- Enable WAL, foreign keys on every connection, bounded lock waits, and explicit
  transaction control. Keep writes short; inference happens after commit. API and
  worker share one local directory on one host; no network-mounted database.
- Only synthetic data in tests. Never inspect live `.env`, provider configs,
  credentials, uploads, or private logs. Use examples and test-generated settings.
- Apply learner ownership and adult authorization in backend services on every
  relevant operation; an opaque UUID is not authorization.
- Export OpenAPI and regenerate frontend types when API consumers are introduced.
  Add drift checks; do not hand-edit generated files.
- Use root Make targets and record exact migration, test, and build outcomes.
  T01 must pass real migration/integration gates before completion; no database
  daemon or Docker is required. Consult docs/HANDOFF.md for T01–T05 boundaries.
