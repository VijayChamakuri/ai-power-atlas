#!/usr/bin/env bash
# Airflow and MLflow share one Postgres; the image only creates POSTGRES_DB on its own.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "CREATE DATABASE mlflow"
