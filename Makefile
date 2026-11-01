.PHONY: setup up down lint test ci sources-check ingest analysis pipeline paper lake-export lake-restore ship clean

setup:
	uv sync --python 3.12
	scripts/link_libomp.sh
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

# Order matters: sites need files, EIA needs sites, candidates need EIA, weather needs candidates.
ingest:
	uv run atlas ingest files
	uv run atlas ingest sites
	uv run atlas ingest eia
	uv run atlas ingest candidates
	uv run atlas ingest weather

analysis:
	uv run atlas analyze detectability
	uv run atlas analyze figures

pipeline: ingest analysis

paper:
	uv run atlas analyze paper

lake-export:
	uv run atlas lake export atlas-m1-frozen-lake.tar.gz

lake-restore:
	uv run atlas lake restore atlas-m1-frozen-lake.tar.gz

ship: ci
	scripts/ship.sh

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache
