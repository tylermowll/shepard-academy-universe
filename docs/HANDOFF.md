# Spark 1.3 handoff: T01–T05

This is a coding handoff, not an application model integration. No call to Spark
or other provider is made by the app in these tasks. The repository is prepared
for one implementation agent working through tasks in order, with evidence after
each task. Model quality is not assumed; completion depends on the checks below.

Read [TASKS.md](TASKS.md) for the current checkpoint, the
[specification roadmap](SPECIFICATION.md#15-implementation-roadmap) for normative
gates, and [DECISIONS.md](DECISIONS.md) for the local-CI, tooling, and SQLite decisions.

## Before T01

Run from the repository root:

```bash
make bootstrap
make hooks-install
make check
make smoke
```

Use Node from `.node-version`, pnpm from `package.json`, and Python from
`.python-version`. See the README for browser setup and writable-cache overrides.
The maintainer authorized the initial commit/push. Local T00 evidence is sufficient
for this handoff; inspect the actual hosted run before claiming CI passed. This
handoff does not authorize additional Git pushes.

**T01 uses SQLite on local disk; no database daemon or Docker is required.**
Follow D004, including SQLAlchemy/Alembic, WAL, per-connection foreign keys,
bounded lock waits, explicit transaction control, and temporary on-disk tests.
T01 owns generated local settings, real migrations, and the integration target
in Make and CI. Do not introduce a second database engine.

First verify `uv run --directory apps/api --locked python -c
"import sqlite3; print(sqlite3.sqlite_version)"`. The preparation runtime loads
3.53.1; current stable is 3.53.4. T01 must establish a reproducible current-stable
embedded runtime (recheck the official release record), or document a justified
compatibility exception under D001. A newer standalone SQLite CLI is insufficient.

Inspect Git status and preserve existing source, including untracked edits.
Hooks installed in one clone do not transfer to another. `make hooks-check` sees
tracked files; stage only reviewed public files. Generate synthetic databases
inside test-owned temporary directories; never commit database binaries/sidecars.

## Task boundaries and evidence

| Task | Implement this increment | Required proof before continuing |
|---|---|---|
| T01 | SQLite/SQLAlchemy/Alembic foundation, initial domain/persistence model, explicit public/private schemas, temporary on-disk integration database | Embedded runtime recorded; empty-file migration; schema/constraint/connection/rollback/reopen/UTC checks; hidden-answer serialization test; `make check`; real `make test-integration` in Make and CI |
| T02 | Adult local bootstrap, password hashing, opaque server sessions, login/logout, CSRF and expiry | Missing/placeholder secrets rejected; cookie flags and CSRF enforced; bad login, expired session, logout and revocation tests |
| T03 | Managed learner aliases, device pairing, ownership checks | Short-lived single-use pairing bound to the requesting browser; revoked/expired device rejected; learner A cannot read/mutate learner B's resources; learner cannot call adult routes |
| T04 | Bounded deterministic fraction generator, safe answer parser and exact verifier | Hypothesis/property tests; A01/A03/A18; equivalent vs simplest-form answers; zero denominators, oversized input, and executable-looking text rejected safely |
| T05 | One persistent fraction exercise, typed answer/revision, immutable built-in profile snapshot, authored hints and visible history | Browser completes an exercise and retains it after reload; exact verdict, assistance and history persisted; duplicate/conflicting requests handled; two-learner isolation and hidden-answer checks still pass |

The first T01 migration should contain real entities required by the initial
increment. Add authentication, pairing, attempts, and later job/provider tables
in the task that actually uses them. Do not create empty modules or all future
entities to imitate the target layout. Preserve the specification's UUID, UTC,
constraint, ownership, and immutable revision requirements as entities are added.

As soon as the frontend consumes backend data, add real `make contracts` and
`make contracts-check` behavior: export FastAPI OpenAPI, generate frontend types,
and reject drift. Do not maintain a second handwritten API schema. Keep grading
and authorization on the server even when the UI performs input checks.

For T05, follow the documented
[staging default](DECISIONS.md#d003--t05-before-the-worker-2026-09-06): immediate,
transactional deterministic checking with a `201` result, then the durable `202`
workflow in T06. This is an explicit preparation assumption; if the maintainer
changes it, update the decision and dependencies before implementation. Do not
invent completed background jobs or remove idempotency/ownership requirements.

Add working Make targets only as their implementation becomes real. T01 adds
database/migration/integration commands; T02 adds adult bootstrap; T05 extends
browser tests from scaffold rendering to a seeded principal workflow. Tests must
use isolated temporary database files and generated synthetic settings, never a
maintainer's configured database. Cleanup may remove only the test's own resources.

## Copyable prompt

```text
Continue this repository from T01 through T05, one task at a time.

First inspect git status. Read AGENTS.md, relevant nested AGENTS.md, README.md,
docs/TASKS.md, docs/HANDOFF.md, docs/DECISIONS.md, the current task's sections in
docs/SPECIFICATION.md, and .agents/skills/implement-task/SKILL.md. Read the skill
explicitly; do not assume your client automatically discovers .agents files.

T00 has local completion evidence. Verify hosted CI status before claiming it
passed. The initial publication was authorized; this task handoff allows no push.
Keep the pinned supported toolchain. TypeScript/Vitest compatibility exceptions
are documented; do not suppress checks or upgrade into known broken combinations.

Start T01 with the SQLite decision D004. Verify/update the SQLite library actually
loaded by Python, then establish temporary on-disk integration databases using
the production connection settings. No Docker/database service is required.
Name affected contracts, migrations, and acceptance tests before editing. Build
the smallest working increment and preserve all existing source, including
untracked files. Generate API types when first needed; never hand-edit them.

After each task, run targeted checks, make check, and its integration/browser
gates. Record exact commands, outcomes, limitations, and changed files in
docs/TASKS.md. Only then continue to the next task. If a real prerequisite or
contract conflict blocks progress, report it and preserve the work; do not skip
tests, introduce a second database engine, or start a later task instead.

T01–T05 use deterministic code and authored help only. No application provider
calls, model downloads, cloud infrastructure, deployment, or Git push. Never
open live .env files, private provider settings, uploads, credentials, or private
logs. Use examples and synthetic fixtures. Stop after T05 and report the working
typed-answer flow and all acceptance evidence for review.
```

## Preparation environment notes

The local review installed Node and pnpm under `/tmp` rather than changing system
packages. For another agent in the same environment, the verified shell setup is:

```bash
export PATH="/tmp/math-tutor-node/node-v24.20.0-linux-x64/bin:/tmp/math-tutor-node/tools/bin:$PATH"
export UV_CACHE_DIR=/tmp/math-tutor-uv-cache
export UV_PYTHON_INSTALL_DIR=/tmp/math-tutor-python
export PRE_COMMIT_HOME=/tmp/math-tutor-pre-commit
export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/google-chrome
make bootstrap PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'
make check PNPM='pnpm --store-dir /tmp/math-tutor-pnpm-store'
make smoke
```

These paths are temporary session conveniences, not portable project defaults.
On another host, install the pinned tools normally. This environment requires
permission to listen on loopback for browser tests; dependency checks do not need
provider credentials. Do not broaden the app's bind address to work around it.
