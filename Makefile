.DEFAULT_GOAL := help

.PHONY: help install dev test test-unit lint format typecheck check db db-stop setup verify clean migrate migration

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies (including dev and test)
	uv sync --extra test --group dev

dev: ## Start local dev server with auto-reload
	uv run uvicorn src.main:app --reload

test: ## Run full test suite (needs postgres)
	uv run pytest

test-unit: ## Run unit tests only (no database needed)
	uv run pytest tests/unit

lint: ## Run ruff linter
	uv run ruff check .

format: ## Format code with ruff
	uv run ruff format .

typecheck: ## Run mypy type checker
	uv run mypy src/

check: lint typecheck ## Run lint + typecheck + format check + unit tests
	uv run ruff format --check .
	uv run pytest tests/unit -q

db: ## Start postgres via docker compose
	docker compose up -d db

db-stop: ## Stop docker compose services
	docker compose down

setup: install db ## Install deps + start database + copy .env
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env from .env.example — fill in your credentials."; \
	else \
		echo ".env already exists, skipping copy."; \
	fi
	@echo ""
	@echo "Done. Next steps:"
	@echo "  1. Edit .env with your GitHub App credentials and API key"
	@echo "  2. make dev"

verify: ## Smoke test: hit /health to check the server is up
	@curl -sf http://localhost:8000/health > /dev/null && echo "OK: server is healthy" || echo "FAIL: server not reachable on port 8000"

migrate: ## Run database migrations to latest
	uv run alembic upgrade head

migration: ## Create a new migration (usage: make migration msg="add foo column")
	uv run alembic revision --autogenerate -m "$(msg)"

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
