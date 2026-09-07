# Implementation tasks

The normative scope, dependencies, deliverables, and exit evidence are in
[specification section 15](SPECIFICATION.md#15-implementation-roadmap). This file
records implementation status; a task is complete only when all of its
specification gates pass.

| Task | Status | Current evidence / next boundary |
|---|---|---|
| T00 | Complete | Local gates and original hosted CI verified; review validation below. |
| T01 | Reviewed; complete | Explicit transactional SQLite, stable/private storage, real rollback/migration/drift gates. Review commit ae3f135 passes local and hosted CI. |
| T02 | Reviewed; complete | Startup/setup, strict origins, expiring CSRF, reset/rotation/revocation, bounded login limits, and session constraints in migration 0002. D005 removes the review's development-schema upgrade bridge; cutover evidence below. |
| T03 | Implemented; automated gates passed | Browser-bound pairing, expiry/revoke and two-learner ownership. |
| T04 | Implemented; automated gates passed | Exact parser/generators; Fraction/property and hostile-input tests. |
| T05 | Implemented; automated gates passed | Persisted practice, answers/steps/help/history and browser completion. |
| T06 | Implemented; automated gates passed | Durable leases, six-call budget, idempotency, crash/deletion recovery. |
| T07 | Implemented; contract-tested | Mock and strict provider policy/errors; no cloud fallback. |
| T08 | Implemented; automated gates passed | Versioned profiles, questions, authored assistance and preview. |
| T09 | Implemented; live verification pending | Meta wire-contract/adult-policy tests; exact account contract must be verified. |
| T10 | Implemented; automated gates passed | Private normalized photos, immutable confirmation and stale-write tests. |
| T11 | Implemented; physical phone evidence pending | HEIF/metadata/bounds tests and browser preview/crop/rotation flow. |
| T12 | Implemented; live unverified | Ollama native text/image contracts; operator setup documented. |
| T13 | Implemented; live unverified | vLLM/compatible bounded wire/capability contracts; runtime/model pending. |
| T14 | Implemented; live unverified | Bedrock Converse SDK Stubber tests; region/model/IAM pending. |
| T15 | Implemented; automated gates passed | Linear equation generator, independent arithmetic properties and exact parser. |
| T16 | Implemented; automated gates passed | Review/progress, authenticated export, deletion and restore tombstones. |
| T17 | Implemented; physical accessibility/phone evidence pending | Public-only PWA caches, manual update, offline/reconnect browser tests. |
| T18 | Implemented; live quality evaluation pending | 33 original rational and 30 rendered vision fixtures, four external fixtures; mock report and A01–A24 mapping. |
| T19 | Implemented; final release acceptance pending | Hardened packaging/backup/restore/docs; local/hosted evidence below; maintainer gates remain. |
| T20 | Implemented; IaC validation passed | Single-host EC2/EBS, private backup S3, IAM/budget runbook; no provisioning. |
| T21 | Implemented; automated gates passed | Public offline pack, exact local answers, no sync or grading authority. |
| T22 | Implemented; automated gates passed | Opt-in external-photo question confirmation; four fixtures remain unverifiable. |
| T23 | Implemented experiment; device measurement pending | Pinned text-only WebLLM research with consent/hash validation/cancel/delete; no weights downloaded. |

## Evidence

Entries below are historical observations. The final SQLite decision entry and
D004 supersede earlier PostgreSQL prerequisites; the initial push authorization
supersedes the earlier push deferral. Historical checks are not database evidence.

### 2026-09-06 — Python/uv backend foundation

- `make bootstrap`: passed using Python 3.13.15 and the committed lockfile.
- `make check`: passed lock freshness, Ruff lint/format, strict mypy, one pytest API
  test, and both sdist and wheel builds.
- Uvicorn smoke test: `GET /health` returned HTTP 200 with `{"status":"ok"}`;
  the temporary localhost server then shut down cleanly.
- Repository skill validation: passed for
  `.agents/skills/implement-task/SKILL.md`.
- Not run: frontend or CI checks; those parts of T00 do not exist yet.

### 2026-09-06 — Review of implemented bootstrap and commit safeguards

Scope: close gaps in the existing backend/development workflow. No T01–T23
features were started, and no application behavior or acceptance gate was relaxed.

Findings and changes:

- Replaced the long blueprint README with current status, tested setup, implemented
  commands, contributor guidance, limitations, and the next bounded task. Preserved
  normative requirements in `docs/SPECIFICATION.md`; roadmap and A01–A24 table rows
  are unchanged. Updated `AGENTS.md` and this task log to point to that authority.
- Added `.pre-commit-config.yaml` using locked `pre-commit` and `pre-commit-hooks`
  development dependencies in `apps/api/pyproject.toml` / `uv.lock`. Added
  `hooks-install`, `hooks-check`, and `pre-commit-check` to `Makefile`.
- Installed the Git pre-commit hook in this checkout. It rejects private paths,
  private key material, merge markers, files over 1 MiB, malformed YAML/TOML, and
  whitespace problems, then runs backend lock/lint/format/type/test checks.
  Added root `secrets/` and `logs/` exclusions to `.gitignore`.
- Added `.github/workflows/ci.yml` for the existing backend with locked setup,
  hooks, and package checks, read-only permissions, a job timeout, and verified
  action commit pins. Recorded tooling resolutions/pins in `docs/DEPENDENCIES.md`.

Actual verification:

- `UV_CACHE_DIR=/tmp/math-tutor-uv-cache make bootstrap`: passed with Python
  3.13.15 and uv 0.12.10; lock resolves 42 packages.
- `UV_CACHE_DIR=/tmp/math-tutor-uv-cache make check`: passed lock freshness, Ruff
  lint/format, strict mypy (4 files), pytest (1 API test), and sdist/wheel builds.
- `uv run --project apps/api --locked pre-commit validate-config
  .pre-commit-config.yaml`: passed (with the writable cache override).
- `make hooks-install`: passed in this checkout and in the temporary fixture.
- In a temporary Git repository containing only reviewed public files, fresh
  `make bootstrap`, `make hooks-install`, `make hooks-check`, `make check`, and an
  initial synthetic commit all passed. Bootstrap used the already installed
  Python 3.13.15 interpreter explicitly via `UV_PYTHON`; dependencies were installed
  into a new virtual environment. Subsequent hook checks ran with `UV_OFFLINE=true`.
- `python3 /tmp/math-tutor-verify-hooks.py`: passed 12 rejected-commit scenarios:
  synthetic `.env`, provider config, upload, private-key marker, merge marker,
  oversized file, malformed YAML, malformed TOML, whitespace, staged invalid Python
  with an unstaged fix, source deletion, and stale lock metadata. The staged/unstaged
  test verified both versions were preserved. Public `.env.example` and
  `providers.example.yaml` committed successfully. These were disposable fixture
  commits; the working repository's index was not changed.
- Local Markdown link/heading validation passed for README, AGENTS, and all three
  docs files. The moved roadmap and acceptance rows were compared with the original
  README and preserved verbatim.
- Environment limitations encountered and resolved: the default uv cache is
  read-only here, so checks used a writable `/tmp` cache. A first offline fresh
  install lacked interpreter discovery and cached packages; the successful fresh
  install explicitly selected the existing interpreter and downloaded locked
  packages. This is not evidence of a fresh Python runtime download.

Readiness and remaining gates:

- The existing backend scaffold and local commit workflow pass their checks.
  **T00 remains in progress.** Finish the React/Vite scaffold, a rendered page,
  one frontend test, and frontend type/lint/build gates in Make and CI. Record a
  hosted CI run after an authorized push before claiming T00 complete.
- After T00, proceed in dependency order through T01–T05 to one persisted fraction
  problem with typed input and deterministic feedback. Provider work comes later.
- Not run: GitHub-hosted CI, frontend/database/integration/end-to-end checks, full
  API-token secret scanning, dependency vulnerability scanning, or any live
  provider/model evaluation. Hosted CI needs a push; the other infrastructure and
  gates are not implemented. Private-key/path checks do not replace broader scans.
- License confirmation and a complete license file remain required before public
  release. No deployment, Git push, model download, or real-data test was performed.
- The repository still has no initial commit; existing public files remain
  untracked and were preserved. Selectively review and stage them before using
  `make hooks-check` on this checkout (it enumerates tracked files).

### 2026-09-06 — Local T00 completion and T01–T05 handoff

The maintainer authorized completing the local foundation and explicitly deferred
pushing/hosted CI evidence. They also requested latest LTS tooling. D001 and D002
in `docs/DECISIONS.md` record the updated baseline and local completion rule; the
historical evidence above remains unchanged.

Changes and contracts satisfied:

- Added `apps/web/` with React/TypeScript/Vite, Tailwind, an honest development
  preview, semantic structure, a JavaScript-disabled fallback, and a component test.
  No practice, authentication, database, or provider feature is claimed.
- Added root pnpm workspace/configuration, exact direct versions, `pnpm-lock.yaml`,
  `.node-version`, strict TypeScript/type-aware ESLint, and Prettier. Added
  `scripts/check-toolchain.mjs` with actionable runtime/package-manager failures.
- Updated `.python-version`, `apps/api/pyproject.toml`, and `uv.lock` for Python
  3.14.7. Current upstream releases were checked online. Node 24.20.0 is latest LTS;
  Python uses its stable support lifecycle. TypeScript 6.0.3, Vitest 4.1.11, and the
  generally available Ubuntu CI runner have documented compatibility exceptions.
- Expanded `Makefile` and `.pre-commit-config.yaml` so frontend locks, lint,
  formatting, types, and component tests are part of the normal gate. pnpm 12's
  multi-document lockfile has its own YAML check; other YAML still requires a
  single valid document. No file is excluded from lockfile syntax validation.
- Added `playwright.config.ts` and `tests/smoke/bootstrap.spec.ts`. `make smoke`
  builds the app, starts fresh loopback API/frontend servers, checks real API health
  and rendering at desktop/mobile sizes, rejects external page requests, checks
  overflow/page errors, and verifies the JavaScript-disabled fallback.
- Updated `.github/workflows/ci.yml` with pinned Node/pnpm setup, current verified
  action SHAs, both stacks' checks, and the browser smoke gate. Added nested API/web
  instructions and `docs/HANDOFF.md` with a copyable Spark prompt, task boundaries,
  database prerequisites, and commands for this environment. Updated README,
  specification, and dependency records to match.
- D003 explicitly resolves the T05/T06 sequencing ambiguity as a preparation
  assumption: immediate transactional checks in T05, durable queued processing in
  T06. Idempotency, ownership, stale-version handling, and immutable profile
  snapshots already apply in T05. The maintainer may still revise this assumption.

Actual commands and outcomes (using the writable paths in HANDOFF.md):

- `make bootstrap PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'`: passed;
  Python 3.14.7, uv 0.12.10, Node 24.20.0, pnpm 12.3.4. Both locks installed.
  Node archive SHA-256 was checked against the official release manifest; Python
  was downloaded via uv. Runtime downloads were development tooling, not models.
- `make check PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'`: passed both
  lock checks, Ruff, type-aware ESLint, Python/frontend formatting, strict mypy and
  TypeScript, 1 pytest API test, 1 Vitest component test, and Python/frontend builds.
- `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome make smoke`: passed
  all 4 tests using Chrome 152.0.7977.82. Desktop/mobile rendering and disabled-JS
  fallback each passed. Servers shut down after the tests. Mobile emulation is not
  a real-device certification.
- `python3 /tmp/math-tutor-verify-t00.py`: in a public-only temporary Git copy,
  fresh Python/frontend environments, `make bootstrap`, `make hooks-install`,
  `make hooks-check`, `make check`, `make smoke`, and an initial synthetic commit
  passed. The fresh install reused downloaded packages and the verified runtimes;
  it did not reuse the existing project's virtual environment or node_modules.
- The same temporary-copy script rejected bad staged TypeScript despite an
  unstaged correction (preserving both versions), a stale frontend lock, source
  deletion, a synthetic private `.env`, and an unsupported Node major. The fixture
  finished clean, and the original index remained untouched.
- Local Markdown link/heading checks and cross-file toolchain-pin checks passed.
  The original repository still has no staged files or initial commit.

Failures resolved during verification:

- Added DOM library types to the browser-test TypeScript configuration.
- Replaced Vitest 5 after reproducible declaration failures; strict checks stay
  enabled and pass on 4.1.11. Details are in D001.
- Local server startup initially failed with sandbox `EPERM`; the same tests
  passed with permission for loopback listeners, without broadening bind hosts.
- Playwright excludes `noscript` from its text matcher. The fallback now contains
  a paragraph; the test asserts that paragraph's visibility and exact text with
  JavaScript disabled. No assertion was removed.
- The generic YAML hook initially rejected pnpm 12's valid multi-document file;
  a dedicated multi-document syntax check now passes alongside frozen-lock checks.

Remaining boundaries:

- **Ready for T01 code work.** This environment has no Docker/Compose/PostgreSQL
  server or client. Establish a real disposable PostgreSQL runtime in T01, then run
  migrations and integration tests. Do not skip these or substitute SQLite.
- T01–T05 implementation remains unstarted. Generated API types are required when
  the first frontend API consumer is implemented; this static preview has none.
- Not run: hosted GitHub CI (maintainer deferred), PostgreSQL integration tests,
  full dependency vulnerability/API-token scans, real-phone testing, or live
  provider evaluations. Those are not represented as passing. No push, deployment,
  cloud provisioning, model download, or real learner data was used.
- Public-release license selection remains pending and does not block local T01.

### 2026-09-06 — Approved SQLite plan and initial publication preparation

The maintainer approved updating the plans to SQLite and explicitly authorized
the initial commit and push of the reviewed repository to `main`. D004 supersedes
the PostgreSQL runtime requirement above. This increment updates the persistence
contract and commit safeguards; it does not implement T01.

Changed files and requirements:

- `docs/DECISIONS.md`: recorded D004, including one-host operation, local storage,
  WAL/foreign keys/lock waits/durability, transaction control, typed persistence,
  migrations, worker claims, backups, and future scaling criteria. Updated D002
  to distinguish initial publication authorization from later task pushes.
- `docs/SPECIFICATION.md`: aligned architecture, configuration, data model,
  integration gates, planned Make commands, T01/T20, local packaging, and AWS
  hosting with SQLite. Replaced PostgreSQL-specific locking and Fargate/RDS with
  the single-host contract. All A01–A24 acceptance rows are preserved.
- `README.md`, root/API `AGENTS.md`, and `docs/HANDOFF.md`: made the supported
  database and T01–T05 instructions consistent. Native T01 no longer needs Docker
  or a database daemon. Later implementation remains one task at a time.
- `docs/DEPENDENCIES.md`: recorded current stable SQLite 3.53.4 from the official
  release history and the actual Python runtime's 3.53.1 library. T01 must resolve
  that runtime gap, verify the embedded version, and add real integration gates.
- `.gitignore` and `.pre-commit-config.yaml`: exclude/block database files and
  WAL/SHM/journal sidecars in any directory. Synthetic test databases are generated
  from source fixtures. This task log records the actual preparation evidence.

Actual verification (using the temporary tool/cache paths in HANDOFF.md):

- `make check PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'`: passed both
  lock checks, Python/frontend lint/format/type checks, 1 pytest and 1 Vitest test,
  Python wheel/sdist builds, and the Vite build.
- `make smoke` with the documented Chrome executable and loopback permission:
  all 4 desktop/mobile browser tests passed; temporary servers shut down.
- `python3 /tmp/math-tutor-verify-sqlite-plan.py`: links/anchors passed in 9
  documents, all 45 specification footnotes resolved, and A01–A24 matched the
  pre-change public snapshot. A disposable Git fixture verified 12 database/
  sidecar names are ignored and rejected by the hook; 3 public fixture/document
  names remain allowed. Only synthetic files were used.
- `git ls-remote --heads origin`: succeeded with no branches returned before
  preparing the first commit. No existing remote history will be overwritten.
- `git diff --cached --check`: passed for the 41 reviewed public files staged
  for the initial commit. `make hooks-check`: all applicable hooks passed,
  including private-key/file hygiene and backend/frontend project checks.
  The first sandboxed run could not open the tracked skill file in read/write
  mode for newline checks; the complete run passed with filesystem permission.
  No check was skipped or weakened to work around the restriction.

T00 remains complete locally and T01 is ready to start using HANDOFF.md. Database
migrations/integration tests, live provider evaluations, real-phone validation,
and release vulnerability scans are not run because their tasks remain unstarted.
Hosted CI requires observing a run after the authorized push; no result is claimed
here. No application deployment, cloud provisioning, or model download is included.

### 2026-09-06 — T01 SQLite foundation (local completion)

T01 implements the D004 persistence foundation with SQLAlchemy 2.0.52 and
Alembic 1.19.2 (locked with greenlet 3.5.5, Mako 1.4.1, MarkupSafe 3.0.3).
No second database engine was introduced.

Changed files and requirements:

- `apps/api/src/math_tutor/settings.py`: one absolute file-backed SQLite path
  from `DATABASE_URL` (default `./data/math_tutor.sqlite3`); non-SQLite schemes
  and `:memory:` are rejected. Embedded-version floor `MIN_SQLITE_VERSION`.
- `apps/api/src/math_tutor/adapters/db/`: engine factory applying
  WAL/foreign-keys/busy-timeout-5000/synchronous-FULL on every connection with
  read-back verification; UUID-as-text and aware-UTC (naive rejected) column
  types; declarative base with a stable naming convention; `PracticeSession`
  and `ProblemInstance` models (FK, status/range checks, per-session position
  uniqueness). `PracticeSession.learner_id` gains its learner FK in T03.
- `apps/api/src/math_tutor/api/schemas.py`: public session/problem schemas
  excluding the hidden expected answer, raw parameters, seed, and ownership
  identifiers.
- `apps/api/src/math_tutor/cli.py` + `make db`: prepare/secure the data
  directory, enforce the SQLite floor, and verify effective PRAGMAs. No daemon,
  no implicit migration.
- `apps/api/alembic.ini` + `apps/api/migrations/`: env wired to app settings
  with batch rendering; migration `0001_practice_tables` with named
  constraints and a downgrade. `make migrate` stops-note included.
- `apps/api/tests/unit/test_public_schemas.py`: hidden-answer, parameter,
  seed, and ownership exclusion tests.
- `apps/api/tests/integration/test_db_foundation.py`: 16 on-disk tests using
  temporary files with production settings — empty-file upgrade to head,
  migration/metadata drift check, per-connection PRAGMA verification,
  FK/check/unique enforcement, transactional rollback, downgrade/re-upgrade,
  reopen persistence, UTC naive-rejection/normalization, UUID round
  trip/rejection, settings resolution/rejection, version floor, CLI `db`
  success/failure, and hidden-answer retention with public exclusion.
- `Makefile`: real `db`, `migrate`, and `test-integration` targets; backend
  `test` now runs `tests/unit` only. `.env.example`: database settings without
  secrets. `.github/workflows/ci.yml`: `make db` runtime/settings check and
  `make test-integration` gate, no database service.
- SQLite runtime decision: the official release history still lists 3.53.4
  (2026-07-24) as current stable, and Python 3.14.7 (2026-08-05, the latest
  3.14 patch) loads 3.53.1; no reproducible newer runtime exists. The
  3.53.2–3.53.4 deltas are follow-up fixes for 3.53.0 regressions, and T01
  uses only long-stable surface covered by the integration suite. Recorded as
  a compatibility exception under D001 with floor 3.53.1, recheck on the next
  tooling update. A standalone SQLite CLI was not substituted.

Actual verification (with `UV_CACHE_DIR`/`UV_PYTHON_INSTALL_DIR` overrides and
a SHA-256-verified Node 24.20.0 provisioned under `/tmp`):

- `python -m pytest tests/unit tests/integration`: 19 passed (3 unit, 16
  integration) on Python 3.14.7 / SQLite 3.53.1.
- `python -m ruff check .`, `ruff format --check .`, `python -m mypy src
  tests` (strict): all pass. `uv lock --check`: 47 packages. `uv build`:
  sdist/wheel pass.
- Frontend (untouched, re-verified): ESLint, Prettier check, root and web
  `tsc --noEmit`, Vitest (1 passed), Vite build — all pass.
- `make db` through make against a temp `DATABASE_URL`: prints the absolute
  path, `sqlite: 3.53.1 (floor 3.53.1)`, and all four effective PRAGMAs.
  Alembic `upgrade head` from empty file succeeds; `make migrate`'s config
  path was fixed after it failed to resolve the ini location.
- Findings fixed, none waived: symbolic-vs-numeric `synchronous` read-back,
  a dict-vs-set test assertion, and mypy variance on the UUID adapter.

Not run: `make check`/`make smoke` wrappers and hosted CI. This sandbox
denies executing workspace binaries (`Operation not permitted`), so bare
console-script Make targets cannot spawn here; every underlying gate was run
via `python -m`/`node` directly instead. Chrome SIGTRAPs on `socketpair`,
so no browser process can launch in this session. The smoke-covered paths
(`GET /health`, static preview) are untouched and the Vite output hashes are
unchanged. CI runs the real wrappers after push; no hosted result is claimed.

Next bounded task: T02 adult bootstrap/login per HANDOFF.md. No push beyond
the authorized one; later task pushes need their own authorization.

### 2026-09-06 — T02 adult bootstrap/login (local completion)

T02 implements the SPEC section 12 authentication slice for the adult
administrator: Argon2id password hashes, opaque server sessions, login/logout
with CSRF and expiry, an interactive bootstrap CLI, and placeholder-secret
rejection. Learner pairing/ownership stays in T03; no provider, job, or
frontend-login work is claimed.

Changed files and requirements:

- `apps/api/pyproject.toml` + `uv.lock`: added `argon2-cffi>=25.1,<26`
  (resolved 25.1.0 with bindings 26.1.0, cffi 2.1.1, pycparser 3.0; 51
  packages). The hasher's default output was verified to be `$argon2id$`.
- `apps/api/src/math_tutor/settings.py`: `SESSION_SECRET` (missing,
  placeholder, or under 32 characters raises; the liveness probe stays
  exempt) and `APP_PUBLIC_ORIGIN` (default `http://localhost:8080`, selects
  the Secure cookie flag and accepted Origin).
- `apps/api/src/math_tutor/adapters/db/models.py` + migration
  `0002_auth_sessions`: `administrator` (unique login name, Argon2id PHC
  hash) and `device_session` (unique SHA-256 token hash, role, adult FK,
  plain `learner_id` until T03 adds its FK, per-session CSRF token,
  expiry, revocation). Downgrade drops both tables.
- `apps/api/src/math_tutor/auth.py`: 24-hour session lifetime, HMAC-signed
  anonymous CSRF bootstrap, salted password hashing, and 10 login
  attempts per minute per client address (over-budget attempts extend the
  wait; `Retry-After` is returned). Task-level parameters, not D-decisions:
  24 h lifetime, 10/min/IP limit, 12-character admin minimum.
- `apps/api/src/math_tutor/api/auth.py` + `api/app.py`: `GET
  /api/v1/auth/session` (minimal status plus CSRF bootstrap, no learner
  list), `POST /api/v1/auth/login` (double-submit CSRF + Origin + rate
  limit, one identical 401 for unknown/wrong credentials), `POST
  /api/v1/auth/logout` (session-bound CSRF, immediate revocation, cookie
  cleared). Session cookies are `HttpOnly`, `SameSite=Lax`, `Secure` on
  https origins, `Path=/`. Responses carry no password/token hashes.
- `apps/api/src/math_tutor/cli.py` + `Makefile` + `.env.example`: real
  `make admin` that prompts for the login name and reads the password twice
  via `getpass` (no `--password` flag, nothing in history/logs), creates or
  resets the administrator with a 12-character minimum, rejects a
  placeholder secret before prompting, and points at `make migrate` when
  tables are missing.
- Tests: 8 unit (`tests/unit/test_auth_secrets.py`: secret accept/reject,
  origin default/override, Argon2id format/verify/salts, anon-CSRF
  round-trip/rejection, token hashing, rate-limit counting) and 18
  integration (`tests/integration/test_auth_sessions.py`: empty-file
  migration with constraint checks, login-name uniqueness, password policy
  and reset, placeholder-secret 500s, cookie flags incl. Secure-on-https,
  response-shape leak checks, shared 401s, CSRF double-submit/forgery,
  Origin rejection, logout CSRF/revocation scoping to the presenting
  session, expired/tampered rejection, HTTP 429 with `Retry-After`, and five
  CLI paths). `test_db_foundation.py` now targets head `0002` with the four
  tables; its drift test covers the new models unchanged.

Actual verification (backend via the venv interpreter directly; the sandbox
denies spawning workspace console scripts, so bare `make` targets were not
used — every underlying gate ran explicitly):

- `.venv/bin/python -m pytest tests/unit tests/integration`: 45 passed
  (11 unit, 34 integration) on Python 3.14.7 / SQLite 3.53.1.
- `.venv/bin/python -m ruff check .`, `ruff format --check .`,
  `.venv/bin/python -m mypy src tests` (strict, 19 files): all pass.
- `uv lock --directory apps/api --check`: fresh (51 packages). `uv build
  --directory apps/api`: sdist/wheel pass.
- Frontend (untouched, re-verified with the provisioned Node 24.20.0):
  ESLint, Prettier check, root and web `tsc --noEmit`, Vitest (1 passed),
  Vite build — all pass. pnpm itself is unavailable in this shell, so the
  exact underlying binaries ran via `node ...` instead of `pnpm` scripts.
- `DATABASE_URL=<tmp> .venv/bin/python -m math_tutor.cli db`: prints the
  absolute path, `sqlite: 3.53.1 (floor 3.53.1)`, and all four PRAGMAs.
- `alembic -c alembic.ini upgrade head` against a temp `DATABASE_URL`:
  succeeds with all four tables plus `alembic_version`.
- Findings fixed, none waived: Pydantic `None` fields excluded from auth
  payloads, detached-instance read moved inside the CLI session, lowercase
  `SameSite=lax` assertion, https base URL for the Secure-cookie test
  (Secure cookies only return over https, matching browsers), and a missing
  settings fixture in the unmigrated-DB CLI test.

Not run: `make check`/`make smoke` wrappers and hosted CI. Chrome SIGTRAPs
in this sandbox so no browser process can launch; the smoke-covered paths
(`GET /health`, static preview) are untouched and the Vite output rebuilds
cleanly. CI runs the real wrappers after push; no hosted result is claimed.

Next bounded task: T03 learners, device pairing, and ownership boundaries
per HANDOFF.md. The maintainer authorized this task's push to `main`.

### 2026-09-06 — Independent T01/T02 review and gap closure

The maintainer requested review of Spark 1.3's T01/T02 work, fixes, a push to
`main`, a model assessment, and a T03 readiness decision. The starting tree was
clean at `17308bb`; Spark's T01 commit was `bf54cc9`. Review addressed T01 first,
then T02, without implementing T03. This request authorizes the review push.

Original hosted evidence was independently observed with `gh run list`:

- [T00: passed](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34046875874).
- [T01: passed](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34067432542).
- [T02: passed](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34071452670).

Findings and fixes, ordered by consequence:

- **High, T01 — transaction guarantees were absent.** The engine retained
  sqlite3's legacy transaction mode despite comments claiming explicit control.
  A created table survived rollback and a read changed within its transaction.
  `adapters/db/engine.py` now disables implicit BEGIN and lets SQLAlchemy issue
  BEGIN; `migrations/env.py` explicitly enables transactional DDL and disposes
  engines. New tests cover DDL/savepoint rollback, stable read snapshots, and a
  deliberately failing migration preserving both schema and data. This follows
  the [SQLAlchemy transaction documentation](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#enabling-non-legacy-sqlite-transactional-modes-with-the-sqlite3-or-aiosqlite-driver).
- **High, T01 — path validation was disconnected from actual connections.**
  Default paths changed with cwd, engines used relative URLs directly, and
  rejected in-memory configurations still reached the engine factory. Settings
  and every engine now resolve the same absolute file, enforce the runtime
  floor and file-only configuration, and prepare mode-0700 storage with mode-0600
  database/sidecars. SQL parameter values are hidden in database exceptions.
- **High, T02 — Origin/Host and startup contracts were incomplete.** A matching
  attacker-controlled Host was trusted, scheme differences were accepted, CSRF
  bootstrap did not check Origin, non-loopback HTTP could issue insecure cookies,
  and missing secrets did not stop startup. The API now validates startup
  configuration and configured Host/full Origin, requires HTTPS off loopback,
  rejects whitespace-only secrets, and prevents caching of API responses.
  Native dev/smoke servers disable forwarded headers. Checks use the configured
  target origin, consistent with the [OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#checking-the-origin-header).
- **Medium, T02 — authentication lifecycle gaps.** Anonymous CSRF expiry was
  only a browser cookie lifetime; signed tokens now carry a server-checked time.
  Password resets now revoke existing sessions, and reauthentication rotates
  tokens/CSRF while revoking the old session. Login rechecks credentials in a
  short write transaction so a concurrent reset cannot create a valid session.
  Lock contention returns a bounded `503`/`Retry-After` without partial writes.
- **Medium, T02 — credential and limiter edge cases.** Bootstrap accepted
  passwords the API rejected (>256 characters), unknown users skipped password
  hashing, and the in-process limiter had unsynchronized/unbounded state. Bounds
  now agree, unknown users perform Argon2id verification, and the one-process
  limiter has atomic admission, fixed windows, and a capped key count. Validation
  errors do not echo credential inputs; CLI errors do not print SQL parameters,
  and password entry refuses a terminal fallback that would echo the password.
- **Medium, T02 — unconstrained session identity.** New migration
  `0003_session_invariants.py` adds role/principal and expiration checks using
  Alembic batch operations. Valid rows survive; invalid legacy rows stop and
  roll back the migration without deletion. Named constraints and foreign keys
  are verified. Migrations 0001 and 0002 were preserved.
- **Setup and evidence gaps.** `cli.py`, `Makefile`, `.env.example`, and README
  now provide `make setup` and explicit environment export instructions; the
  old advice to copy `.env` alone did not load settings. Setup generates a random
  secret and absolute URL, creates a private file exclusively, and never reads
  or overwrites an existing one. `playwright.config.ts` supplies isolated
  synthetic settings for startup; CI's `make db` uses a temporary path.
  Database tests now hold two independent connections concurrently (the old
  test reused one pooled connection) and compare all four tables and their
  constraints, including failed-migration/data-preservation cases. The UTC
  adapter also rejects tzinfo objects that supply no offset.

Actual verification:

- Before fixes, added T01 regressions produced **7 failures / 16 passes**;
  added T02 checks reproduced **5 failures** for startup, Origin, reset,
  cache headers, and password bounds. The first HTTP expiry test exercised
  browser cookie expiration; it was corrected to replay a captured cookie and
  complemented by direct server-token expiry/future-time tests.
- After T01 fixes: `make check PNPM='pnpm --store-dir
  /tmp/math-tutor-pnpm-store'` passed, and `make test-integration` passed
  **42 tests** before the T02 review changes.
- After all fixes: `apps/api/.venv/bin/python -m pytest apps/api/tests/unit
  apps/api/tests/integration -q` passed **85 tests**, up from 45 original cases.
  This is 22 unit tests and 63 on-disk integration tests; all data is synthetic.
- Final `make check PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'` passed
  both locks, lint/format, strict mypy (19 files), TypeScript, 22 pytest unit
  tests, 1 Vitest test, wheel/sdist, and Vite builds. Its first run caught seven
  strict mypy import errors in new tests; those were fixed without suppressions.
- `make test-integration`: **63 passed**. Coverage includes concurrent reset
  during login, replay/revocation, untrusted Origin/Host, concurrent limiter
  admission, a real five-second SQLite lock wait/retry, and migration rollback.
- `make smoke`: **4 passed** (desktop/mobile Chromium, including the
  JavaScript-disabled fallback). Temporary servers shut down after the tests.
- `make db` and `make migrate` against an exclusively generated `/tmp` database:
  SQLite **3.53.1**, WAL, foreign keys **1**, busy timeout **5000**, synchronous
  **FULL**; empty-file upgrade through **0003** succeeded. The temporary files
  were removed afterward.
- Commands used the documented `/tmp` Node/Python/cache overrides. A sandboxed
  ASGI run stalled and was interrupted; the synthetic integration/browser gates
  passed with execution permission. No test policy was disabled. `git diff
  --check` and `git diff --cached --check` passed. `make hooks-check` passed all
  applicable file/privacy, lock, lint/format/type, and unit/component checks.
  Commit `ae3f135` was pushed to `main`; [its full hosted CI run passed](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34072697983)
  in 1m31s, including locked installs, hooks, Make checks, SQLite runtime,
  integration, and browser smoke gates. A documentation follow-up records this
  observed result and warns existing installations to retain their absolute
  database URL when adopting the corrected default path.

Assessment of Spark's original work: **5/10 overall for these two tasks**, a
qualitative review judgment rather than a general model benchmark. It produced
useful, organized code, real migrations, separate public schemas, maintained
password hashing, locked dependencies, and passing CI. Its main weakness was
verifying the difficult contracts: tests covered ordinary paths while missing
transactions, trust boundaries, and lifecycle cases, and some comments/evidence
claimed guarantees the implementation did not provide. The fixes were
substantive. This sample supports using it for bounded implementation with
independent review, especially for persistence and authentication. No inference
speed, token use, or cost measurements were available for a throughput comparison.

**T03 is ready to start after this reviewed foundation.** Its bounded work is
managed aliases/eligibility, a real learner table plus ownership foreign keys,
single-use expiring pairing bound to the requesting browser, adult approval,
revocation, and two-learner read/mutation isolation with learner rejection from
adult routes. Generate API contracts if a frontend consumer is introduced.
T03 is not implemented by this review.

Not run: live/paid provider inference, model downloads, deployment, real learner
data, real-phone testing, or release vulnerability scans. These are outside
T01/T02; the SQLite compatibility exception remains D001. No runtime/private
configuration was opened, and no live database was migrated.

### 2026-09-06 — Maintainer-directed pre-production cutover

The maintainer clarified that nothing is in production and requested hard
cutovers without legacy bloat. D005 and `AGENTS.md` record that policy for future
work. This supersedes the preceding review's development-database upgrade plan;
the historical test/CI observations above remain observations of those commits.

- Folded session identity/lifetime constraints into migration
  `0002_auth_sessions.py` and deleted `0003_session_invariants.py`. There is one
  current schema and no bridge for previous development databases. README now
  directs users to recreate disposable development databases.
- Updated both integration suites to head 0002. Removed the two legacy-upgrade
  cases and added a current-schema test proving administrator authentication and
  opaque sessions survive an engine reopen. Kept empty-file migrations,
  constraints, foreign-key checks, DDL/savepoint rollback, failed-migration
  atomicity, expiry/revocation, ownership-principal checks, and secret exclusion.
- `make test-integration`: **62 passed**. `make check
  PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'`: all locks, lint/format,
  strict types, **22 unit + 1 frontend tests**, and Python/Vite builds passed.
  The current backend total is **84 tests**; the count change follows the removed
  compatibility behavior. No failing assertion was suppressed.
- `make db` and `make migrate` passed against a fresh, private `/tmp` database
  through the corrected head 0002; the generated database was removed afterward.
  `make hooks-check` and `git diff --cached --check` passed.
- The preceding documentation commit `99c5286` also passed its
  [hosted CI run](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34072857295).
  The cutover push/hosted CI are verified separately after this entry.

The assessment of Spark's original code remains **5/10 for T01/T02**. The removed
compatibility migration was added during this review, not by Spark. T03 remains
ready to start. No private database/configuration was opened or reset, and no
provider, deployment, or model-download work was performed.


### 2026-09-06 — Authorized completion of remaining implementation

The maintainer approved MIT, the remaining repository scope, end-batched checks,
hard cutovers and push to main. They deferred the items requiring physical devices
or provider accounts. D006 records the sequencing/schema decisions. The table
above distinguishes implementation from external acceptance; T19/T23 are not
claimed fully accepted without that evidence.

Affected contracts/files:

- `apps/api/migrations/versions/0001*` through `0008*`, ORM/domain/API/worker code:
  real learner ownership, pairing, exact skills, immutable profile/interpretation
  versions, durable work and call budgets, provider routes/probes, retention/audit.
- Provider transports/config and typed DTOs; generated `contracts/openapi.json`
  and `apps/web/src/generated/api.d.ts`, including separate work/final-answer fields.
- React practice/adult/photo/research components, safe math rendering, offline pack,
  service worker/update behavior and mobile/desktop workflows.
- Backup/restore and private S3 archive CLI, Docker/Compose/Caddy/CloudFormation,
  Make/CI checks, original eval fixtures and reports, MIT and operational docs.

Validation observed during implementation:

- `make check`: passed locks, Ruff lint/format, strict mypy (46 files), strict
  TypeScript, 60 backend unit tests, 3 frontend component tests, package/Vite
  builds, contract drift, tracked secret scan, and CloudFormation lint. Subsequent
  small capability/concurrency changes receive the final run recorded below.
- `make test-integration`: 80 passed, including four external-problem cases,
  migrations/rollback/ownership, provider recovery and encrypted restore.
- `pnpm smoke`: 12 passed on desktop/mobile Chromium before adding final pairing
  and disconnect coverage. Final full browser outcome is recorded below.
- `make eval-mock`: 33 exact rational cases and 30 mock-vision cases passed. This
  measures software orchestration, not model accuracy or handwriting quality.
- `make audit`: Python and pnpm reported no known vulnerabilities after updating
  cryptography from vulnerable 49.0.0 to fixed 50.0.1 (PYSEC-2026-3552).
- `make infra-check`: CloudFormation lint passed; no AWS resources were created.

Defects found and corrected by these checks included SQLite's unsupported direct
foreign-key alteration (changed to Alembic batch mode), a stale ORM test fixture,
restored WAL changes not reaching the copied database (explicit close/checkpoint),
a Vite worker module-format mismatch, a browser selector mismatch, and the
cryptography advisory. An initial browser invocation omitted this environment's
installed Chrome override; rerunning with the documented executable passed.
Checks were not weakened and no legacy compatibility bridge was added.

Not run: live Meta/Ollama/vLLM/compatible/Bedrock inference, account IAM validation,
model downloads, actual phone Safari/Chrome camera/install/background checks,
WebGPU model/device measurements, cloud provisioning or public deployment. The
maintainer checklist is in ACCEPTANCE. The original Spark T01/T02 assessment remains
5/10 for that observed work; these later implementations do not change its score.

Final local source validation: `make check` passed with **61 unit tests**, **3
component tests**, strict mypy/TypeScript, both builds and all contract/secret/IaC
checks. `make test-integration` passed **81 tests**, including simultaneous worker
claims. Both dependency audits passed and the 63-case synthetic evaluation passed.
`pnpm smoke` passed **14 desktop/mobile browser tests**, including disconnect after
submission, second-browser pairing/revocation, photo confirmation, offline cache,
and user-controlled updates. The disconnect test checks the actual server-failure
banner because browser online hints can remain true while requests are blocked.
`make hooks-check` and `git diff --check` passed on the reviewed staged files.
Visual review found an assistance-history display inconsistency; the final answer
turn now snapshots prior assistance, matching progress. Its focused workflow test
and captured browser scenario passed after the fix. The screenshot in
`docs/screenshots/synthetic-practice.png` contains only a generated synthetic alias
and exercise. It is presentation evidence, not a correctness test.

Docker is not installed in this workspace; the release container build, runtime
smoke and image scan are executed by hosted CI after the authorized push. A clean
checkout rehearsal and observed hosted result will be recorded separately.


Clean-clone rehearsal of implementation commit `9c81e37820dce43193d416bd427bd68a5bf93e29`:
`git clone --no-hardlinks` into a new `/tmp` checkout, `make bootstrap` with a
writable pnpm store, `make smoke` (**14 passed**) and `make test-integration`
(**81 passed**) all succeeded. Fresh virtualenv and node_modules were created;
the previously installed pinned Python runtime/package caches were reused.
The clone's tracked working tree remained clean. No operator settings were copied.
Hosted verification is [run 34078898044](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34078898044);
it passed source/unit/integration gates but failed two browser flows because an
older learner-list request could replace a newer list after creation. A focused
component regression reproduced the empty selection (one failure out of four),
and the adult panel now discards superseded refresh results. Original browser
assertions remain unchanged. The CI failure-context step now prints only synthetic
browser snapshots to make any further timing failures reviewable.

Follow-up recovery review applied the same response-order protection to session
selection/polling, with a second component regression. A subsequent browser run
exposed a logout `503` when a worker write invalidated its deferred read snapshot.
Logout now reserves its short write transaction before reading the session; an
on-disk competing-writer regression verifies this boundary. Authentication and
browser assertions were retained, with no retries or timeout relaxation.

The recovery fixes passed `make test-integration` (**82 tests**), `pnpm test`
(**5 component tests**), strict frontend types/lint, and `make smoke` (**14 browser
tests**). External-mode feedback now explicitly explains its missing trusted
answer key instead of suggesting a different numeric format. CI packaging runs
as a separate required job; no gate or failed assertion was disabled.

The same transaction-boundary review reproduced a stale photo assignment during
image decoding: the upload originally accepted version 1 after another connection
advanced it to version 2. Post-decode authorization now expires cached ORM state
inside the reacquired write transaction; the regression requires `409` and zero
submissions. Provider probes likewise refresh authorization state after I/O.

Hosted [run 34079742050](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34079742050)
passed the complete source job: 61 unit, 83 integration, 5 component and 14 browser
tests, generated contracts, synthetic evaluation and dependency audits. Its package
job built the image and passed non-root API/UI/worker/migration checks, then failed
the strict image scan on inherited OS/installer packages. D007 records the minimal
runtime correction. Public CI visibility and the checked-in synthetic-only job
were verified before reading scanner output; no private application logs were read.

Hosted [run 34080218959](https://github.com/tylermowll/shepard-academy-universe/actions/runs/34080218959)
passed the complete package job: image build, non-root API/UI/worker readiness,
migrations, HEIF/cryptography runtime checks, strict HIGH/CRITICAL scan (including
unfixed findings), and SBOM generation. Its source job exposed three intermittent
browser failures in learner creation/pairing. An independent database reader at
the ASGI success-header boundary reproduced the cause: the default request-scoped
yield dependency committed after sending the response, allowing immediate browser
reads to see old state. The transaction dependency now uses FastAPI's function
scope, completing the commit before success. The new regression failed before
the fix and passed afterward. This complements the earlier stale-response guards;
no browser assertions, retries, timeouts, or scan severity were relaxed.

Final transaction fix validation: `make check` passed all source/build/contract/
secret/IaC gates with **61 backend unit tests** and **5 frontend component tests**;
`make test-integration` passed **84 tests**; `make smoke` passed **14 desktop/mobile
browser tests**. `git diff --check` passed. Hosted CI verifies the pushed revision
with its own fresh environment and the required packaging job.
