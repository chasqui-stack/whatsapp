.PHONY: dev install test

dev:
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

install:
	uv sync

test:
	uv run pytest
