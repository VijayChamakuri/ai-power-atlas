from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas import cli
from atlas.config import Settings
from atlas.source_check import Result, Source, Status


def run_with_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: Status
) -> tuple[int, str]:
    def fake_checks(_: Settings) -> list[Result]:
        return [Result(Source("sample", 1, "https://example.org"), status)]

    monkeypatch.setattr(cli, "run_checks", fake_checks)
    report = tmp_path / "status.md"
    result = CliRunner().invoke(cli.app, ["sources", "check", "--output", str(report)])
    return result.exit_code, report.read_text()


@pytest.mark.parametrize("status", ["ok", "page_only"])
def test_reachable_sources_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: Status
) -> None:
    exit_code, _ = run_with_status(monkeypatch, tmp_path, status)
    assert exit_code == 0


@pytest.mark.parametrize("status", ["needs_key", "blocked", "rate_limited", "unreachable"])
def test_failed_source_exits_1_and_still_writes_the_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: Status
) -> None:
    exit_code, report = run_with_status(monkeypatch, tmp_path, status)
    assert exit_code == 1
    assert status in report
