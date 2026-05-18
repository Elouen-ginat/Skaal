.PHONY: install dev lint format typecheck pyright test test-cov test-storage test-schema \
        hooks audit ci clean help docs docs-serve docs-build

# ── Environment ────────────────────────────────────────────────────────────────
PYTHON  ?= python
PIP     ?= pip
PYTEST  ?= pytest
RUFF    ?= ruff
MYPY    ?= mypy
PYRIGHT ?= pyright

help:
	@echo "Skaal — common dev tasks"
	@echo ""
	@echo "  make install     install package + dev dependencies (editable)"
	@echo "  make dev         alias for install"
	@echo ""
	@echo "  make lint        run ruff check"
	@echo "  make format      run ruff format (writes changes)"
	@echo "  make typecheck   run mypy on skaal/"
	@echo "  make pyright     run pyright (strict via pyrightconfig.json)"
	@echo "  make hooks       run all pre-commit hooks against the working tree"
	@echo "  make audit       run pip-audit against installed deps"
	@echo ""
	@echo "  make test        run pytest"
	@echo "  make test-cov    run pytest with coverage (terminal + html)"
	@echo "  make test-storage|test-schema  scoped suites"
	@echo ""
	@echo "  make ci          full local pre-flight: lint + typecheck + hooks + tests"
	@echo ""
	@echo "  make docs        alias for docs-serve"
	@echo "  make docs-serve  serve the MkDocs site locally with live reload"
	@echo "  make docs-build  build the static site into ./site"

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	$(PIP) install -e ".[dev]"

dev: install
	@echo "Dev environment ready."

# ── Quality ────────────────────────────────────────────────────────────────────
lint:
	$(RUFF) check skaal tests examples

format:
	$(RUFF) format skaal tests examples
	$(RUFF) check --fix skaal tests examples

typecheck:
	$(MYPY) skaal

pyright:
	$(PYRIGHT)

hooks:
	pre-commit run --all-files

audit:
	pip-audit --strict --skip-editable

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	$(PYTEST) tests/ -q

test-cov:
	$(PYTEST) tests/ --cov=skaal --cov-report=term-missing --cov-report=html -q

test-storage:
	$(PYTEST) tests/storage/ -q

test-schema:
	$(PYTEST) tests/schema/ -q

# Run the same checks CI runs, in roughly the same order.
ci: lint typecheck hooks test

# ── Docs ───────────────────────────────────────────────────────────────────────
docs: docs-serve

docs-serve:
	uv run --group docs mkdocs serve

docs-build:
	uv run --group docs mkdocs build --strict

# ── Cleanup ────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf dist/ build/ .coverage coverage.xml htmlcov/ .mypy_cache/ .ruff_cache/ .pytest_cache/
