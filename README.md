# Math Practice Tutor

A self-hosted math practice app in development. The planned workflow is to assign a
problem, accept typed or photographed work, verify supported mathematics with exact
arithmetic, and help the learner revise. The initial topics are fractions and
introductory one-variable linear equations.

## Current status

**T00–T02 pass their local gates. This is a development scaffold, not a usable tutor.**

| Area | Implemented today |
|---|---|
| Backend | Packaged Python 3.14 / FastAPI application with typed `GET /health` response and adult session endpoints (`GET /api/v1/auth/session`, `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`) |
| Database | SQLite/SQLAlchemy/Alembic foundation with migrations 0001–0002, explicit transactions, private storage, UUID/UTC adapters, constrained practice/authentication tables, and public/private schemas |
| Frontend | React/TypeScript/Vite preview with Tailwind, an availability notice, and a JavaScript-disabled fallback |
| Quality checks | Locked dependencies, Python/frontend lint/format/types/tests/builds, on-disk SQLite integration tests, desktop/mobile browser smoke tests |
| Development workflow | Pre-commit checks and a full-stack GitHub Actions workflow; T00–T02 hosted runs verified, with review evidence in the task log |
| Authentication | Adult bootstrap via `make admin`, Argon2id password hashes, opaque sessions with CSRF/expiry/revocation; learner pairing arrives in T03 |
| Tutoring, providers, deployment | Not implemented |

The detailed [specification](docs/SPECIFICATION.md) describes planned behavior.
[Task status and evidence](docs/TASKS.md) record what has actually passed. No live
provider has been tested, and the scaffold is not ready for real learner data or
public deployment.

## Quick start

Run commands from the repository root. Prerequisites:

- Git and GNU Make in a POSIX shell (Linux, macOS, or WSL).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) `>=0.12.10,<0.13`.
- [Node.js](https://nodejs.org/en/download) 24.20.0 (latest LTS), pinned in `.node-version`.
- pnpm 12.3.4: with Node installed, run `npm install --global pnpm@12.3.4`.

Verified versions and compatibility exceptions are recorded in
[DEPENDENCIES.md](docs/DEPENDENCIES.md) and [DECISIONS.md](docs/DECISIONS.md).

```bash
make bootstrap
make hooks-install
make check
make dev-web
```

Open <http://127.0.0.1:5173> for the frontend preview. In a second terminal, run
`make dev-api` for the API. Both development servers use loopback only.

Bootstrap installs locked backend dependencies in `apps/api/.venv` and frontend
workspace dependencies in `node_modules`; uv can download Python 3.14.7 if missing.
The first install requires network access to package/runtime sources. There is no
model or API key at this stage. Before starting the API, run the following from
the repository root:

```bash
make setup
set -a
. ./.env
set +a
make db
make migrate
make admin
make dev-api
```

`make setup` generates a mode-0600 `.env` with an absolute SQLite path and a random
session secret. It refuses to read or overwrite an existing file; if one already
exists, configure it locally using `.env.example` and skip setup. The application
reads exported environment variables, so repeat the export lines in each new
shell. Never share the file or its contents with a coding agent.

Without an override, storage resolves to the checkout's ignored `data/` directory
regardless of working directory. Relative SQLite URLs resolve within that data
directory. An installed package outside a checkout needs an absolute
`DATABASE_URL` or `MATH_TUTOR_DATA_DIR`. All database entrypoints enforce private
directory/file permissions. `make migrate` requires application writes stopped.
`make admin` creates or resets the named administrator interactively; reset revokes
that administrator's existing sessions. Passwords must contain 12–256 characters.

The project is pre-production and uses hard cutovers ([D005](docs/DECISIONS.md#d005--pre-production-hard-cutovers-2026-09-06)).
Recreate any disposable database made before this review, then run `make migrate`
and `make admin`. Earlier development schemas have no upgrade path.

Startup rejects missing/placeholder session secrets and invalid public origins.
The development origin is `http://127.0.0.1:8000`; use that exact address for the
API. Non-loopback origins require HTTPS. Requests must use the configured Host
and, when supplied, the exact Origin. Native development disables proxy headers;
a future gateway deployment must explicitly scope its trusted proxies.

Open <http://127.0.0.1:8000/health>; the expected response is `{"status":"ok"}`.
API documentation is at <http://127.0.0.1:8000/docs>. Stop the server with
`Ctrl+C`. The health endpoint checks only that the API process responds; it does
not assert database, worker, or provider readiness. The development server binds
to loopback by default.

For browser smoke tests, install Chromium once with `pnpm exec playwright install
chromium`, then run `make smoke`. This builds the app, starts fresh API and frontend
servers on loopback ports 18000 and 4173, and stops them afterward. It refuses to
reuse an existing server. On Linux, Playwright may also need its documented system
dependencies (`pnpm exec playwright install --with-deps chromium`). To use an
already installed Chrome, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its binary.
Mobile checks use browser emulation; they do not certify real-phone behavior.

If uv reports a read-only cache in a restricted environment, set `UV_CACHE_DIR`
to a writable directory when running Make. A restricted pnpm store can be set with
`make bootstrap PNPM='pnpm --store-dir /path/to/writable/store'`. If port 8000 is
occupied, stop the other process or run `uv run --directory apps/api --locked uvicorn
math_tutor.api.app:app --reload --port 8001`.

## Development commands

The [Makefile](Makefile) is the authority for commands that exist today.

| Command | Behavior |
|---|---|
| `make bootstrap` | Verify Node/pnpm and install both locked development environments |
| `make setup` | Generate a private local settings file without reading or overwriting one |
| `make toolchain-check` | Reject unsupported Node or mismatched pnpm versions with setup guidance |
| `make hooks-install` | Install the local Git pre-commit hook; repeat for each clone |
| `make hooks-check` | Run hook checks against all tracked files |
| `make check` | Check both locks, Python/frontend lint, formatting, types, tests, and builds |
| `make smoke` | Build and run API/frontend browser smoke tests, including JavaScript-disabled fallback |
| `make pre-commit-check` | Run Python/frontend checks without builds or browser startup |
| `make test` | Run backend unit and frontend component tests |
| `make test-integration` | Run on-disk SQLite integration tests in isolated temporary files |
| `make db` | Validate the SQLite path, embedded runtime version, and connection settings |
| `make migrate` | Apply reviewed Alembic migrations with application writes stopped |
| `make admin` | Interactively create or reset the adult administrator (password via prompt, never argv) |
| `make lint` / `make format-check` | Check Python/frontend lint or formatting without changing files |
| `make format` | Format Python/frontend files; review and stage the changes yourself |
| `make typecheck` | Run strict mypy and TypeScript over source, tests, and configuration |
| `make build` | Build Python packages in `apps/api/dist/` and the frontend in `apps/web/dist/` |
| `make lock` / `make lock-check` | Reconcile both lockfiles / check freshness without rewriting them |
| `make dev-api` | Run the API with reload on loopback port 8000 |
| `make dev-web` | Run the frontend with reload on loopback port 5173 |

For a reviewed dependency upgrade, use `uv lock --directory apps/api
--upgrade-package <name>`, inspect `uv.lock`, update
[DEPENDENCIES.md](docs/DEPENDENCIES.md), and run the checks. Commit the lockfile
with its dependency metadata. Only add dependencies when an implemented task
needs them.

For frontend dependencies, update the relevant workspace's exact package version
and regenerate `pnpm-lock.yaml` with `make lock`. Review compatibility and both
lockfiles, update the dependency record, then run `make check` and `make smoke`.

### Commit checks and CI

The [pre-commit configuration](.pre-commit-config.yaml) uses tools from the same
uv lockfile as development. It blocks private configuration/runtime paths,
SQLite databases and their sidecars, private key material, merge markers,
oversized files, invalid YAML/TOML, and whitespace
errors, then runs both backend and frontend checks. Formatting checks do not stage
changes.
The [pre-commit framework](https://pre-commit.com/#pre-commit) temporarily sets
aside unstaged changes to check the staged revision and restores them afterward.

`make hooks-check` uses Git's tracked-file list. Stage only reviewed public source
files so new files are included; do not use a blanket add of local data.
Hooks can be bypassed, and private-key detection is not a general
API-token or learner-data scanner. Review staged content yourself; broader secret
and dependency vulnerability scanning remain release requirements.

[Project CI](.github/workflows/ci.yml) runs locked setup, the same hooks, and
`make check` and `make smoke` on pushes and pull requests. It has read-only
repository permissions, uses actions pinned to commit SHAs, and needs no provider
credentials. The original T00, T01, and T02 hosted runs have been observed passing.
T01 added the SQLite runtime check and on-disk integration gate to CI; T02's auth
tests run inside the existing unit and integration gates. The task log separates
those historical runs from the review changes and their validation.

## Architecture and implementation order

The planned stack is a React/TypeScript/Vite PWA, a FastAPI modular monolith,
SQLite on local disk, and a separate worker from the same backend codebase.
The initial deployment serves one household on one host; API and worker share
one private data directory. Native setup needs no database daemon or Docker.
Domain code owns exact arithmetic and verdicts; adapters isolate model providers. Photos require
transcription confirmation before grading. Providers cannot change permissions,
answer keys, or workflow state, and local failures cannot silently send work to a
cloud service. See the [architecture contract](docs/SPECIFICATION.md#5-application-architecture).

The next task is T03: managed learner aliases, device pairing, and ownership
checks. Then follow T04–T05 toward one persisted fraction problem with a typed
answer and deterministic feedback. AI integration follows that working slice.
[HANDOFF.md](docs/HANDOFF.md) contains the Spark 1.3 prompt, per-task gates, and
database runtime prerequisites. Do not skip unfinished gates or treat the full
roadmap as one implementation task.

The approved [SQLite decision](docs/DECISIONS.md#d004--sqlite-for-the-initial-deployment-2026-09-06)
defines WAL, connection settings, migrations, job claims, and consistent backups.
T01 implemented the foundation with migration 0001 and T02 added the
administrator/device-session tables in migration 0002, including session
identity/lifetime constraints. The embedded SQLite floor
is 3.53.1 with a documented exception (see D001). Multiple application hosts and
network-mounted database files are outside this design.

## Contributing and documentation

Read [AGENTS.md](AGENTS.md), [TASKS.md](docs/TASKS.md), and the relevant
[specification sections](docs/SPECIFICATION.md) before editing. Keep each change
bounded, name affected contracts/tests, preserve unrelated edits, and record actual
commands and outcomes in the task log. Run `make hooks-check` and `make check`
before requesting review, plus `make smoke` for UI/workflow changes. The repository
uses AI-assisted development; acceptance claims still require test evidence and
maintainer review.

Use synthetic fixtures only. Never commit credentials, private provider settings,
learner data, uploads, or private logs. Paid inference, model downloads, cloud
provisioning, deployment, and Git pushes require maintainer authorization.

MIT is proposed, but **no license has been selected or added yet**. The maintainer
must confirm and add the complete license before public release; dependencies,
model weights, and third-party content retain their own licenses.
