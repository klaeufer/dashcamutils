init:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run ty check

test:
	uv run pytest

check: lint typecheck test

.PHONY: init lint typecheck test check
