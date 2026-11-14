.PHONY: dev test lint

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest

lint:
	ruff check app tests
	mypy app
