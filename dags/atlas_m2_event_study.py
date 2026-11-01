"""The locked test from Amendment 4. Paused so that a person, not a scheduler, starts it.

Before the freeze date the CLI refuses to run, whatever Airflow does. Open-Meteo's daily limit
can stop the weather pull, and the retries resume it the next day.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from atlas_common import DEFAULT_ARGS, atlas

with DAG(
    "atlas_m2_event_study",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 12, 15),
    schedule="@once",
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    tags=["atlas", "m2"],
) as dag:
    snapshot = BashOperator(
        task_id="ingest_m2",
        bash_command=atlas("ingest m2"),
        retries=14,
        retry_delay=timedelta(hours=8),
    )
    event_study = BashOperator(task_id="event_study", bash_command=atlas("analyze event-study"))
    snapshot >> event_study
