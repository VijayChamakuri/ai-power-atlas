import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).parents[2] / "scripts" / "hooks" / "strip-ai-trailers.sh"


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        "Co-authored-by: Codex <noreply@openai.com>",
        "Claude-Session: abc123",
        "Generated with [Claude Code](https://claude.com/claude-code)",
    ],
)
def test_hook_removes_trailer_and_keeps_message(tmp_path: Path, trailer: str) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(f"feat(ingest): paginate EIA pulls\n\nWhy it changed.\n\n{trailer}\n")

    subprocess.run([str(HOOK), str(message)], check=True)

    assert message.read_text() == "feat(ingest): paginate EIA pulls\n\nWhy it changed.\n\n"
    assert not (tmp_path / "COMMIT_EDITMSG.bak").exists()
