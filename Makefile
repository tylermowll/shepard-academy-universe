UV ?= uv
PNPM ?= pnpm
API_PROJECT := apps/api
UV_PROJECT_ARGS := --directory $(API_PROJECT)

.PHONY: bootstrap setup toolchain-check lock lock-check db migrate admin dev-api dev-web test \
	test-integration lint format format-check typecheck build check hooks-install \
	hooks-check pre-commit-check smoke

bootstrap: toolchain-check
	$(UV) sync $(UV_PROJECT_ARGS) --locked
	$(PNPM) install --frozen-lockfile

toolchain-check:
	@command -v node >/dev/null || { echo "Install Node.js from .node-version first (see README)."; exit 1; }
	node scripts/check-toolchain.mjs

hooks-install:
	$(UV) run --project $(API_PROJECT) --locked pre-commit install

hooks-check:
	$(UV) run --project $(API_PROJECT) --locked pre-commit run --all-files

lock:
	$(UV) lock $(UV_PROJECT_ARGS)
	$(PNPM) install --lockfile-only

lock-check:
	$(UV) lock $(UV_PROJECT_ARGS) --check
	$(PNPM) install --lockfile-only --frozen-lockfile --ignore-scripts

db:
	$(UV) run $(UV_PROJECT_ARGS) --locked python -m math_tutor.cli db

migrate:
	@echo "Stop API/worker writes before migrating."
	$(UV) run $(UV_PROJECT_ARGS) --locked alembic -c alembic.ini upgrade head

admin:
	$(UV) run $(UV_PROJECT_ARGS) --locked python -m math_tutor.cli admin

setup:
	$(UV) run $(UV_PROJECT_ARGS) --locked python -m math_tutor.cli setup

dev-api:
	$(UV) run $(UV_PROJECT_ARGS) --locked uvicorn math_tutor.api.app:app --reload --no-proxy-headers

dev-web:
	$(PNPM) dev:web

test:
	$(UV) run $(UV_PROJECT_ARGS) --locked pytest tests/unit
	$(PNPM) test

test-integration:
	$(UV) run $(UV_PROJECT_ARGS) --locked pytest tests/integration

lint:
	$(UV) run $(UV_PROJECT_ARGS) --locked ruff check .
	$(PNPM) lint

format:
	$(UV) run $(UV_PROJECT_ARGS) --locked ruff format .
	$(PNPM) format

format-check:
	$(UV) run $(UV_PROJECT_ARGS) --locked ruff format --check .
	$(PNPM) format:check

typecheck:
	$(UV) run $(UV_PROJECT_ARGS) --locked mypy src tests
	$(PNPM) typecheck

build:
	$(UV) build $(UV_PROJECT_ARGS)
	$(PNPM) build

pre-commit-check: toolchain-check lock-check lint format-check typecheck test

check: pre-commit-check build contracts-check secret-check infra-check

smoke: build
	$(PNPM) smoke

.PHONY: contracts contracts-check secret-check audit eval-mock eval-live dev serve demo worker test-e2e infra-check backup restore

contracts:
	$(UV) run --project $(API_PROJECT) --locked python scripts/export-contracts.py --output contracts/openapi.json
	$(PNPM) --filter @math-tutor/contracts generate
	$(PNPM) exec prettier --write apps/web/src/generated/api.d.ts

contracts-check:
	$(UV) run --project $(API_PROJECT) --locked python scripts/check-contracts.py

secret-check:
	$(UV) run --project $(API_PROJECT) --locked python scripts/scan-secrets.py

audit:
	sh scripts/audit-python.sh
	$(PNPM) audit

infra-check:
	$(UV) run --project $(API_PROJECT) --locked cfn-lint infra/aws/household.json

eval-mock:
	$(UV) run --project $(API_PROJECT) --locked python -m math_tutor.evaluation --fixtures evals/fixtures/rational-v1.json --output evals/reports/deterministic.json

eval-live:
	@test -n "$(PROVIDER)" || { echo "Set PROVIDER to an explicitly configured provider ID."; exit 1; }
	$(UV) run --project $(API_PROJECT) --locked python -m math_tutor.evaluation --fixtures evals/fixtures/rational-v1.json --output evals/reports/live-synthetic.json --live-provider "$(PROVIDER)" --authorize-synthetic-calls --max-calls 3

dev: build
	$(UV) run --project $(API_PROJECT) --locked python scripts/dev.py

# A separately configured HTTPS gateway forwards to loopback port 8000.
serve: build
	$(UV) run --project $(API_PROJECT) --locked python scripts/dev.py --gateway

demo: build
	$(UV) run --project $(API_PROJECT) --locked python scripts/serve-demo.py --port 8000

worker:
	$(UV) run $(UV_PROJECT_ARGS) --locked python -m math_tutor.worker

test-e2e: smoke

backup:
	@test -n "$(OUTPUT)" || { echo "Set OUTPUT to a new encrypted backup path; stop writes first."; exit 1; }
	$(UV) run --project $(API_PROJECT) --locked python -m math_tutor.backup backup "$(OUTPUT)" --writes-stopped

restore:
	@test -n "$(INPUT)" -a -n "$(OUTPUT)" -a -n "$(LEDGER)" || { echo "Set INPUT, a new OUTPUT directory, and the current LEDGER path; stop writes first."; exit 1; }
	$(UV) run --project $(API_PROJECT) --locked python -m math_tutor.backup restore "$(INPUT)" --destination "$(OUTPUT)" --deletion-ledger "$(LEDGER)" --writes-stopped

.PHONY: seed-demo down
seed-demo:
	$(UV) run --project $(API_PROJECT) --locked python -m math_tutor.demo

down:
	docker compose -f infra/docker/compose.yaml down
