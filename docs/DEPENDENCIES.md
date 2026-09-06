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

Only dependencies used by the current scaffold are installed. Add database,
provider, image, and property-testing packages in the task that first uses them.

## Planned persistence baseline

The approved SQLite plan is [D004](DECISIONS.md#d004--sqlite-for-the-initial-deployment-2026-09-06).
SQLite has no separate LTS edition; its current stable release is **3.53.4**,
verified against the [official release history](https://sqlite.org/changes.html).
The current Python 3.14.7 interpreter reports **3.53.1** from
`sqlite3.sqlite_version`. This is a recorded T01 runtime gap, not a claim that
3.53.1 is latest or that persistence has been tested.

T01 selects a reproducible Python runtime linked to current stable SQLite and
checks the embedded version in setup/CI. It adds supported stable SQLAlchemy 2
and Alembic releases to the lockfile when implementing persistence. Use the
standard sqlite3 driver; a standalone SQLite CLI does not determine its version.

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
still a GitHub Public preview (see D001). No hosted CI run is claimed.

Sources: [Node releases](https://nodejs.org/en/about/previous-releases),
[Python downloads](https://www.python.org/downloads/),
[uv locking](https://docs.astral.sh/uv/concepts/projects/),
[uv build backend](https://docs.astral.sh/uv/configuration/build-backend/),
[PyPI metadata](https://pypi.org/), [npm registry](https://registry.npmjs.org/),
[pnpm settings](https://pnpm.io/settings), [Vite](https://vite.dev/guide/),
[Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite),
[Playwright web servers](https://playwright.dev/docs/test-webserver).
