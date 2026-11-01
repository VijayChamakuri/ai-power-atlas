"""DAGs hold order and schedule only. All logic stays in the atlas CLI and the dbt project."""

from datetime import timedelta

PROJECT = "/opt/atlas/project"
BIN = "/opt/atlas/venv/bin"
DEFAULT_ARGS = {"owner": "vijay", "retries": 2, "retry_delay": timedelta(minutes=10)}


def atlas(command: str) -> str:
    return f"cd {PROJECT} && {BIN}/atlas {command}"


def dbt(selection: str) -> str:
    return (
        f"cd {PROJECT} && mkdir -p data && {BIN}/dbt build --project-dir dbt --profiles-dir dbt "
        f"--no-use-colors --target lake --target-path ../data/dbt/airflow "
        f"--log-path data/dbt/logs {selection}"
    )
