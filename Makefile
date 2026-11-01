.PHONY: setup up down lint test ci sources-check clean

setup:
	uv sync --python 3.12
	test -f .env || cp .env.example .env
	git rev-parse --git-dir >/dev/null 2>&1 || git init -b main
	git config user.name "Vijay Shankar Chamakuri"
	git config user.email "vijaychamakuri1558@gmail.com"
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

up:
	docker compose up -d --wait

down:
	docker compose down

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

test:
	uv run pytest

ci: lint test

sources-check:
	uv run atlas sources check

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache
