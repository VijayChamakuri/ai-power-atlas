"""The full M1 rebuild, in the order `make pipeline` uses. Manual only, since M1 is frozen."""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from atlas_common import DEFAULT_ARGS, atlas, dbt

with DAG(
    "atlas_rebuild",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 10, 31),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["atlas", "m1"],
) as dag:
    steps = [
        BashOperator(task_id="ingest_files", bash_command=atlas("ingest files")),
        BashOperator(task_id="ingest_sites", bash_command=atlas("ingest sites")),
        BashOperator(task_id="ingest_eia", bash_command=atlas("ingest eia")),
        BashOperator(task_id="ingest_candidates", bash_command=atlas("ingest candidates")),
        BashOperator(task_id="ingest_weather", bash_command=atlas("ingest weather")),
        BashOperator(task_id="detectability", bash_command=atlas("analyze detectability")),
        BashOperator(task_id="figures", bash_command=atlas("analyze figures")),
        BashOperator(task_id="dbt_build", bash_command=dbt("--exclude tag:recent")),
    ]
    for upstream, downstream in zip(steps, steps[1:], strict=False):
        upstream >> downstream
