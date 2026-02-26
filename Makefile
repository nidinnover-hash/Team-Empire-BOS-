.PHONY: help dev test lint typecheck security audit coverage check migrate clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev:  ## Start dev server on port 8002
	uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload

test:  ## Run full test suite
	python -m pytest tests/ -q

lint:  ## Run ruff linter
	ruff check app tests

typecheck:  ## Run mypy type checker
	python -m mypy

security:  ## Run bandit security lint
	bandit -r app -ll -q

audit:  ## Run pip-audit for known CVEs
	pip-audit -r requirements.txt --progress-spinner off

coverage:  ## Run tests with coverage report
	python -m pytest tests/ -q --cov=app --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=61

check:  ## Run all pre-launch checks (lint + typecheck + security + audit + tests + coverage)
	@echo "=== Lint ==="
	ruff check app tests
	@echo "=== Type Check ==="
	python -m mypy
	@echo "=== Security Lint ==="
	bandit -r app -ll -q
	@echo "=== Dependency Audit ==="
	pip-audit -r requirements.txt --progress-spinner off
	@echo "=== Dependency Integrity ==="
	python -m pip check
	@echo "=== Tests + Coverage ==="
	python -m pytest tests/ -q --cov=app --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=61
	@echo "=== All checks passed ==="

migrate:  ## Run alembic migrations
	python -m alembic upgrade head

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f coverage.xml .coverage
