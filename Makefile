# BotForge developer tasks. Run `make help` for the list.
COMPOSE := docker compose -f infra/docker-compose.yml
API := apps/api
WEB := apps/web

.PHONY: help up down logs dev-api dev-web install lint fmt typecheck test test-api test-web migrate seed clean-devdata

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## Start the full dev stack (postgres, redis, api, worker, web, n8n, ollama)
	$(COMPOSE) up

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Tail stack logs
	$(COMPOSE) logs -f

dev-api: ## Run the API locally with reload
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

dev-web: ## Run the web app locally
	cd $(WEB) && npm run dev

install: ## Install all dependencies
	cd $(API) && uv sync
	cd $(WEB) && npm install

lint: ## Lint api (ruff) and web (eslint)
	cd $(API) && uv run ruff check .
	cd $(WEB) && npm run lint

fmt: ## Format api (ruff) and web (prettier via eslint)
	cd $(API) && uv run ruff format . && uv run ruff check --fix .

typecheck: ## Typecheck api (mypy) and web (tsc)
	cd $(API) && uv run mypy app
	cd $(WEB) && npx tsc --noEmit

test: test-api test-web ## Run all tests

test-api: ## Run backend tests
	cd $(API) && uv run pytest -q

test-web: ## Run frontend tests (build acts as the check until vitest lands)
	cd $(WEB) && npm run build

migrate: ## Apply database migrations (Phase 1+)
	cd $(API) && uv run alembic upgrade head

seed: ## Seed demo data (Phase 1+)
	cd $(API) && uv run python -m app.db.seed

clean-devdata: ## Remove ephemeral @example.com test users/orgs + the live_demo flag (dev only)
	cd $(API) && uv run python -m app.db.cleanup_devdata
