# Implementation tasks

The normative scope, dependencies, deliverables, and exit evidence are in
[specification section 15](SPECIFICATION.md#15-implementation-roadmap). This file
records implementation status; a task is complete only when all of its
specification gates pass.

| Task | Status | Current evidence / next boundary |
|---|---|---|
| T00 | Complete locally | Fresh locked installs, backend/frontend checks/builds, commit hooks, and 4 browser smoke tests pass. Initial push authorized; hosted CI evidence pending (D002). |
| T01 | Complete locally | SQLite/SQLAlchemy/Alembic foundation with migration 0001, public/private schemas, and on-disk integration gates pass. Hosted CI evidence pending; no push beyond the authorized one. |
| T02 | Not started | Blocked by its roadmap dependency. |
| T03 | Not started | Blocked by its roadmap dependency. |
| T04 | Not started | Blocked by its roadmap dependency. |
| T05 | Not started | Blocked by its roadmap dependencies. |
| T06 | Not started | Blocked by its roadmap dependency. |
| T07 | Not started | Blocked by its roadmap dependency. |
| T08 | Not started | Blocked by its roadmap dependency. |
| T09 | Not started | Blocked by its roadmap dependency. |
| T10 | Not started | Blocked by its roadmap dependency. |
| T11 | Not started | Blocked by its roadmap dependency. |
| T12 | Not started | Blocked by its roadmap dependency. |
| T13 | Not started | Blocked by its roadmap dependency. |
| T14 | Not started | Blocked by its roadmap dependency. |
| T15 | Not started | Blocked by its roadmap dependencies. |
| T16 | Not started | Blocked by its roadmap dependencies. |
| T17 | Not started | Blocked by its roadmap dependencies. |
| T18 | Not started | Blocked by its roadmap dependencies. |
| T19 | Not started | Blocked by its roadmap dependency. |
| T20 | Not started | Blocked by its roadmap dependency. |
| T21 | Not started | Blocked by its roadmap dependency. |
| T22 | Not started | Blocked by its roadmap dependency. |
| T23 | Not started | Blocked by its roadmap dependency. |

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
