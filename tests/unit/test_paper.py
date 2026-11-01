from pathlib import Path

from atlas.ml.paper import render_html


def test_formula_underscores_survive_markdown() -> None:
    html = render_html("Test $t - 365$ days.\n\n$$\\sum_{d=t}^{t+179} r_d$$\n", Path("/repo"))
    assert "$$\\sum_{d=t}^{t+179} r_d$$" in html
    assert "$t - 365$" in html


def test_figures_point_at_real_files_and_tables_render() -> None:
    figure = '<p align="center"><img src="docs/fig.png" width="860" alt="A"></p>'
    readme = f"{figure}\n\n| a |\n|---|\n| 1 |\n"
    html = render_html(readme, Path("/repo"))
    assert 'src="file:///repo/docs/fig.png"' in html
    assert "<table>" in html
