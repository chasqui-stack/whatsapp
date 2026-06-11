.PHONY: dev install test

# Development server (port from .env PORT, default 8000)
dev:
	uv run python -c "import uvicorn; from app.core.config import settings; uvicorn.run('app.main:app', host='0.0.0.0', port=settings.port, reload=True)"

install:
	uv sync

test:
	uv run pytest
