# Dependency baseline

Verified September 6, 2026. `pyproject.toml` uses bounded direct requirements so
intent and compatibility remain visible; the exact, cross-platform resolution is
committed in `apps/api/uv.lock` and installed with `--locked`.

| Dependency | Declared / tested resolution | Purpose |
|---|---:|---|
| Python | 3.14 / 3.14.7 | Latest stable line; Python has no separate LTS edition |
| uv CLI | `>=0.12.10,<0.13` / 0.12.10 | Environment and lock management; pin exactly in CI |
| uv_build | `>=0.12.10,<0.13` / bundled 0.12.10 | Pure-Python build backend |
| FastAPI | `>=0.141.1,<1` / 0.141.1 | HTTP API framework |
| Pydantic | `>=2.13.5,<3` / 2.13.5 | Public and internal typed schemas |
| Uvicorn | `>=0.52.4,<1` / 0.52.4 | Local ASGI server |
| HTTPX2 | `>=2.12,<3` / 2.12.0 | Maintained in-process API test client used by Starlette |
| pytest | `>=9.1.1,<10` / 9.1.1 | Backend tests |
| Ruff | `>=0.16.6,<1` / 0.16.6 | Formatting and linting |
| mypy | `>=2.3.1,<3` / 2.3.1 | Static type checking |
| pre-commit | `>=4.6.2,<5` / 4.6.2 | Git hook installation and staged-change isolation |
| pre-commit-hooks | `>=6.0.0,<7` / 6.0.0 | Repository hygiene and private-key checks |
| SQLAlchemy | `>=2,<3` / 2.0.52 | SQLite persistence, ORM, and transaction control (T01) |
| Alembic | `>=1.16,<2` / 1.19.2 | Versioned SQLite migrations (T01) |
| argon2-cffi | `>=25.1,<26` / 25.1.0 | Argon2id adult password hashing; `$argon2id$` default verified (T02) |
| argon2-cffi-bindings | transitive / 26.1.0 | Native Argon2 backend for argon2-cffi (T02) |
| cffi | transitive / 2.1.1 | Foreign-function interface for the bindings (T02) |
| pycparser | transitive / 3.0 | C parser for cffi (T02) |
| greenlet | transitive / 3.5.5 | SQLAlchemy optional concurrency support (T01) |
| Mako | transitive / 1.4.1 | Alembic migration templating (T01) |
| MarkupSafe | transitive / 3.0.3 | Mako escaping dependency (T01) |

Only dependencies used by implemented tasks are installed. The completed roadmap
adds the provider, image, backup and evaluation dependencies recorded below.

## Persistence baseline (T01 implemented)

The approved SQLite plan is [D004](DECISIONS.md#d004--sqlite-for-the-initial-deployment-2026-09-06).
SQLite has no separate LTS edition; its current stable release is **3.53.4**,
verified against the [official release history](https://sqlite.org/changes.html)
on September 6, 2026. The Python 3.14.7 interpreter (2026-08-05, the latest
3.14 patch) reports **3.53.1** from `sqlite3.sqlite_version`; no reproducible
newer runtime exists, so T01 records a compatibility exception under D001 with
an enforced floor of 3.53.1 instead of claiming 3.53.1 is latest.

T01 added supported stable SQLAlchemy 2 and Alembic releases to the lockfile,
checks the embedded version in `make db`/CI, and covers the relied-upon
surface with on-disk integration tests. The standard sqlite3 driver is used;
a standalone SQLite CLI does not determine its version.

## Frontend and browser tooling

Node.js **24.20.0** is the latest LTS and is pinned in `.node-version`. pnpm
**12.3.4** is pinned in the root `packageManager` field. `pnpm-lock.yaml` records
exact transitive resolutions and integrity hashes; installs use `--frozen-lockfile`.
Project scripts reject unsupported Node and mismatched pnpm versions. Dependency
install scripts are blocked unless explicitly reviewed in `pnpm-workspace.yaml`.

The versions below were checked against official npm metadata on September 6,
2026 and tested together. TypeScript 6.0.3 and Vitest 4.1.11 are explicit compatible
stable exceptions to newer releases; see [D001](DECISIONS.md#d001--supported-toolchain-baseline-2026-09-06)
for evidence. No `skipLibCheck`, lint suppression, or relaxed peer resolution is used.

| Package | Pinned version |
|---|---:|
| `@eslint/js` | 10.0.1 |
| `@playwright/test` | 1.63.0 |
| `@tailwindcss/vite` | 4.3.3 |
| `@testing-library/dom` | 10.4.1 |
| `@testing-library/jest-dom` | 7.0.1 |
| `@testing-library/react` | 16.3.3 |
| `@types/node` | 24.13.3 |
| `@types/react` | 19.2.18 |
| `@types/react-dom` | 19.2.7 |
| `@vitejs/plugin-react` | 6.1.1 |
| `eslint` | 10.10.0 |
| `eslint-plugin-react-hooks` | 7.1.1 |
| `eslint-plugin-react-refresh` | 0.5.6 |
| `globals` | 17.12.0 |
| `jsdom` | 30.0.1 |
| `prettier` | 3.9.6 |
| `react` | 19.2.8 |
| `react-dom` | 19.2.8 |
| `tailwindcss` | 4.3.3 |
| `typescript` | 6.0.3 |
| `typescript-eslint` | 8.69.0 |
| `vite` | 8.2.2 |
| `vitest` | 4.1.11 |

## CI tool pins

Hook commands use uv-locked development packages and pnpm-locked frontend tools;
there are no separately resolved hook environments. CI pins uv to 0.12.10 and
Node via `.node-version`; pnpm/action-setup reads the exact root `packageManager`.

| Action | Release | Verified commit |
|---|---|---|
| actions/checkout | v6.1.0 | `d23441a48e516b6c34aea4fa41551a30e30af803` |
| actions/setup-node | v6.5.0 | `249970729cb0ef3589644e2896645e5dc5ba9c38` |
| pnpm/action-setup | v5.0.0 | `fc06bc1257f339d1d5d8b3a19a8cae5388b55320` |
| astral-sh/setup-uv | v7.6.0 | `37802adc94f370d6bfd71619e3f0bf239e1f3b78` |

Pins were checked against the official repositories' release refs on September 6,
2026. Ubuntu 24.04 is the latest generally available Ubuntu LTS runner; 26.04 is
still a GitHub Public preview (see D001). See TASKS for observed hosted CI runs.

Sources: [Node releases](https://nodejs.org/en/about/previous-releases),
[Python downloads](https://www.python.org/downloads/),
[uv locking](https://docs.astral.sh/uv/concepts/projects/),
[uv build backend](https://docs.astral.sh/uv/configuration/build-backend/),
[PyPI metadata](https://pypi.org/), [npm registry](https://registry.npmjs.org/),
[pnpm settings](https://pnpm.io/settings), [Vite](https://vite.dev/guide/),
[Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite),
[Playwright web servers](https://playwright.dev/docs/test-webserver).

## T03–T23 additions

| Package | Locked resolution | Purpose |
|---|---|---|
| boto3 / botocore | 1.43.89 | Bedrock Converse and explicit S3 archive transport |
| boto3-stubs / service stubs | 1.43.89 / exact per-service versions in uv.lock | Development-only schema typing; service packages have independent release numbers |
| Pillow | 12.3.0 | Bounded raster normalization and original synthetic fixtures |
| pillow-heif | 1.7.0 | HEIC/HEIF decoder |
| cryptography | 50.0.1 | Authenticated encrypted backup format |
| PyYAML / types-PyYAML | uv.lock | Strict operator configuration and development typing |
| Hypothesis | 6.167.1 | Exact arithmetic properties |
| pip-audit | 2.10.1 | Audit all locked Python dependencies |
| cfn-lint | 1.56.0 | Local CloudFormation validation; transitive SymPy is development-only IaC tooling, never a learner-text evaluator |
| KaTeX / @types/katex | 0.18.6 / 0.16.8 | Restricted trusted-false math rendering |
| @mlc-ai/web-llm | 0.2.84 | Optional isolated browser research; no weights bundled |
| openapi-typescript | 7.13.0 | Generated frontend API schemas |
| tools/contracts TypeScript | 5.9.3 | Isolated generator peer compatibility; application remains 6.0.3 |

The Python lock resolves 97 packages including development tools. The first audit
identified PYSEC-2026-3552 in cryptography 49.0.0; upgrading to 50.0.1 cleared the
Python audit. The pnpm audit also passed. There is no vulnerability suppression.
Run audits again for release; an earlier pass is not a permanent security claim.

Container bases are digest-pinned in `infra/docker/Dockerfile`; public registry
metadata was verified before pinning. The runtime uses uv-managed Python to retain
the tested embedded SQLite version. CI scans HIGH/CRITICAL findings including
unfixed ones with Trivy action v0.36.0 pinned to
`ed142fd0673e97e23eac54620cfb913e5ce36c25`, and generates a CycloneDX SBOM.
A failed image scan must be fixed or receive a separately documented reviewed
exception; it is never silently ignored. See TASKS for the actual image scan result.

Browser-model files are pinned by exact public repository revision and individual
hashes in `research-manifest.json`. These are metadata, not downloaded weights.
Actual runtime/model/device interoperability remains a maintainer gate (T23).

The first hosted image scan found inherited Debian 12 utilities and unused Python
installer packages (60 OS and two installer findings). D007 replaces the runtime
base with a pinned Distroless Debian 13 image and removes unused installer code.
It retains the exact managed Python/SQLite runtime and locked app dependencies.
The scan threshold and unfixed-vulnerability policy remain unchanged.
