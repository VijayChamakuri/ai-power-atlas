"""Airflow is not in this environment, so DAG files are read as text and their commands checked."""

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas import cli

DAGS = sorted((Path(__file__).parents[2] / "dags").glob("atlas_*.py"))
COMMAND = re.compile(r'atlas\("([^"]+)"\)')


def _commands() -> list[str]:
    return [command for path in DAGS for command in COMMAND.findall(path.read_text())]


def test_dags_exist() -> None:
    assert _commands()


@pytest.mark.parametrize("command", _commands())
def test_dag_commands_exist_in_the_cli(command: str) -> None:
    assert CliRunner().invoke(cli.app, [*command.split(), "--help"]).exit_code == 0


def test_scheduled_dags_that_spend_or_decide_start_paused() -> None:
    for name in ("atlas_eia_recent.py", "atlas_m2_event_study.py"):
        path = next(path for path in DAGS if path.name == name)
        assert "is_paused_upon_creation=True" in path.read_text()
