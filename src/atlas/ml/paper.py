"""PDF of the README, so the paper can be read or sent without a GitHub login."""

import re
import subprocess
from pathlib import Path

import markdown

KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STYLE = """
@page { size: letter; margin: 0.85in 0.9in; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.42;
       color: #1a1a1a; }
h1 { font-size: 21pt; line-height: 1.15; text-align: center; margin: 0 0 4pt; }
h1 + h3 { text-align: center; font-weight: normal; font-style: italic; font-size: 12pt;
          margin: 0 0 8pt; }
h1 + h3 + p { text-align: center; }
h2 { font-size: 13pt; margin: 16pt 0 5pt; break-after: avoid; }
h3 { font-size: 11pt; margin: 11pt 0 4pt; break-after: avoid; }
p { margin: 0 0 7pt; }
blockquote { margin: 8pt 0; padding: 6pt 10pt; background: #f2f1ed;
             border-left: 2.5pt solid #5f5f5a; }
blockquote p { margin: 0; }
hr { border: 0; border-top: 0.6pt solid #b9b8b2; margin: 10pt 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 6pt 0 10pt;
        font-family: Helvetica, Arial, sans-serif; break-inside: avoid; }
th { text-align: left; border-top: 1pt solid #1a1a1a; border-bottom: 0.6pt solid #1a1a1a;
     padding: 3pt 5pt; }
td { border-bottom: 0.3pt solid #d4d3cd; padding: 3pt 5pt; vertical-align: top; }
a { color: #1a5ea8; text-decoration: none; }
code { font-size: 9pt; }
pre { background: #f2f1ed; padding: 6pt 8pt; font-size: 9pt; }
.figure { text-align: center; margin: 9pt 0 5pt; break-after: avoid; break-inside: avoid; }
.figure img { max-width: 100%; max-height: 8.0in; }
.figure + p { font-size: 9.2pt; line-height: 1.32; font-family: Helvetica, Arial, sans-serif; }
"""


def _protect_math(text: str) -> tuple[str, list[str]]:
    """Markdown would read the underscores in formulas as emphasis."""
    held: list[str] = []

    def hold(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f"MATHTOKEN{len(held) - 1}X"

    text = re.sub(r"\$\$.+?\$\$", hold, text, flags=re.DOTALL)
    return re.sub(r"(?<![\w$])\$[^$\n]+?\$(?![\w$])", hold, text), held


def render_html(readme: str, root: Path) -> str:
    protected, held = _protect_math(readme)
    body = markdown.markdown(protected, extensions=["tables", "fenced_code"])
    for index, formula in enumerate(held):
        body = body.replace(f"MATHTOKEN{index}X", formula)
    body = re.sub(
        r'<p align="center">\s*<img src="([^"]+)"([^>]*?)/?>\s*</p>',
        lambda match: (
            f'<div class="figure"><img src="{(root / match.group(1)).as_uri()}"'
            f"{match.group(2)}></div>"
        ),
        body,
    )
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Can a Single AI Data Center Be Seen in US Grid Demand?</title>
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body, {{delimiters: [
    {{left: '$$', right: '$$', display: true}}, {{left: '$', right: '$', display: false}}]}})">
</script><style>{STYLE}</style></head><body>{body}</body></html>"""


def build_pdf(readme: Path, html_path: Path, pdf_path: Path) -> None:
    html_path.write_text(render_html(readme.read_text(), readme.parent.resolve()))
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--no-pdf-header-footer",
            "--virtual-time-budget=20000",
            f"--print-to-pdf={pdf_path.resolve()}",
            html_path.resolve().as_uri(),
        ],
        check=True,
        capture_output=True,
    )
