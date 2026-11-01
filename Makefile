.PHONY: setup up down lint test dbt-ci dbt-build ci sources-check ingest analysis pipeline paper lake-export lake-restore lake-sample m2 m2-early clean

DBT_ARGS := --project-dir dbt --profiles-dir dbt --no-use-colors

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
	uv run sqlfluff lint dbt/models dbt/tests

test:
	uv run pytest

# Builds every model and test on the real slice in tests/fixtures/lake, so CI needs no MinIO.
dbt-ci:
	mkdir -p data
	ATLAS_LAKE_ROOT="$(CURDIR)/tests/fixtures/lake" uv run dbt build $(DBT_ARGS) --target fixture \
		--target-path ../data/dbt/fixture --log-path data/dbt/logs

# The rolling pull has its own DAG, so a frozen rebuild does not need it to have run.
dbt-build:
	mkdir -p data
	uv run --env-file .env dbt build $(DBT_ARGS) --target lake --exclude tag:recent \
		--target-path ../data/dbt/lake --log-path data/dbt/logs

ci: lint test dbt-ci

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

# Rewrites the real slice CI builds on, from the frozen lake.
lake-sample:
	uv run atlas lake sample tests/fixtures/lake

# Refuses to run before the freeze date in Amendment 4.
m2:
	uv run atlas ingest m2
	uv run atlas analyze event-study

# Amendment 5: Meta Los Lunas only. Runs once, then refuses.
m2-early:
	uv run atlas ingest m2-early
	uv run atlas analyze event-study-early

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache
