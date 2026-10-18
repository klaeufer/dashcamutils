init:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run ty check

check: lint typecheck

.PHONY: init lint typecheck check
