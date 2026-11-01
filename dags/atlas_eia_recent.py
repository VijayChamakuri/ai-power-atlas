"""Pulls the last 72 hours every hour, because EIA revises recent hours. dbt keeps the latest.

Paused until switched on: it is the only DAG that spends API calls on a schedule.
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from atlas_common import DEFAULT_ARGS, atlas, dbt

with DAG(
    "atlas_eia_recent",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 11, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    tags=["atlas", "incremental"],
) as dag:
    pull = BashOperator(task_id="pull", bash_command=atlas("ingest eia-recent"))
    build = BashOperator(task_id="dbt_build", bash_command=dbt("--select +tag:recent"))
    pull >> build
