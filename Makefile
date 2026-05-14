MAYBE_SOURCE = $(wildcard session-environment.sh)
MAYBE_SOURCE_CMD = $(if $(MAYBE_SOURCE),source $(MAYBE_SOURCE) &&,)

.DEFAULT_GOAL := help

.PHONY: help install lint lintfix format typecheck secscan test test-unit precommit clean

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies via uv
	uv sync --all-groups

lint: ## Run ruff check
	uv run ruff check src tests

lintfix: ## Run ruff with automated fixing and formatting
	uv run ruff check --fix src tests
	uv run ruff format src tests

format: ## Run ruff format
	uv run ruff format src tests

typecheck: ## Run mypy static type checking
	uv run mypy src

secscan: ## Run semgrep and bandit security scanners
	uv run semgrep --config=auto src
	uv run bandit -r src

test: ## Run all tests
	uv run pytest

test-unit: ## Run unit tests only (exclude integration)
	uv run pytest -m "not integration"

precommit: lint typecheck secscan test ## Run full pre-commit suite

clean: ## Remove build artifacts
	rm -rf dist build .mypy_cache .ruff_cache .pytest_cache \
		src/xplane_gen/__pycache__ tests/__pycache__
