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

check: pre-commit-check build

smoke: build
	$(PNPM) smoke
