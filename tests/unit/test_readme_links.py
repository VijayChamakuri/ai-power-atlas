"""Relative links in the README and the working paper have to resolve in the repo."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISHED = (ROOT / "README.md", ROOT / "docs" / "paper.md")


def _targets(path: Path) -> list[str]:
    text = path.read_text()
    return re.findall(r"\[[^\]]*\]\(([^)]+)\)", text) + re.findall(r'<img[^>]+src="([^"]+)"', text)


def test_published_markdown_links_resolve() -> None:
    missing: list[str] = []
    for path in PUBLISHED:
        for url in _targets(path):
            if url.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = url.split("#", 1)[0]
            if target and not (path.parent / target).exists():
                missing.append(f"{path.relative_to(ROOT)} -> {url}")
    assert missing == []
