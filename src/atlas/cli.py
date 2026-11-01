from datetime import UTC, datetime
from pathlib import Path

import structlog
import typer

from atlas.config import Settings
from atlas.source_check import render_report, run_checks

app = typer.Typer(no_args_is_help=True)
sources_app = typer.Typer(no_args_is_help=True)
app.add_typer(sources_app, name="sources")


@app.callback()
def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ]
    )


@sources_app.command("check")
def sources_check(output: Path = Path("docs/source_status.md")) -> None:
    """Exits 1 unless every source returned records or a page, because M0 gates on that."""
    results = run_checks(Settings())
    output.write_text(render_report(results, datetime.now(UTC)))
    if any(result.status not in ("ok", "page_only") for result in results):
        raise typer.Exit(code=1)
