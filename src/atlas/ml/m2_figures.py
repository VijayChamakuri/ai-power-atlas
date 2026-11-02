"""M2 panels. Kept apart from figures.py, which must never show demand after a site starts."""

from datetime import date
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from atlas.config import BA_NAMES, POST_DAYS
from atlas.ml.detectability import null_threshold
from atlas.ml.event_study import rank_p
from atlas.ml.figures import BLUE, DARK, FAINT, INK, MUTED, ORANGE, TEXT_BOX, _panel, _save

# Wide enough that 45 windows stack into a readable shape, narrow enough to keep it.
DOT_BIN_MW = 10.0


def stacked_dots(values: np.ndarray, width: float) -> np.ndarray:
    """Stacks by bin but keeps each dot at its true value, so none crosses a line it does not."""
    bins = np.floor(values / width)
    order = np.argsort(values, kind="stable")
    heights = np.empty(len(values), dtype=int)
    heights[order] = pd.Series(bins[order]).groupby(bins[order]).cumcount().to_numpy() + 1
    return heights


def early_result_figure(
    ba: str, start: date, daily: pd.Series, nulls: np.ndarray, estimate: float, path: Path
) -> None:
    # Matplotlib accepts dates in these calls, though its type stubs only declare float.
    moment: Any = pd.Timestamp(start, tz="UTC")
    window_end: Any = moment + pd.Timedelta(days=POST_DAYS)
    is_before = daily.index < moment
    before = float(daily[is_before].mean())
    after = float(daily[~is_before].mean())

    figure = plt.figure(figsize=(7.4, 4.9))
    grid = figure.add_gridspec(2, 1, height_ratios=[1.15, 1], hspace=0.55)
    top = figure.add_subplot(grid[0])
    top.axvspan(moment, window_end, color=BLUE, alpha=0.06, linewidth=0)
    top.axhline(0, color=FAINT, linewidth=0.6)
    top.plot(daily.index, daily, color=FAINT, linewidth=0.5)
    top.plot(daily[is_before].index, [before] * int(is_before.sum()), color=INK, linewidth=1.4)
    top.plot(daily[~is_before].index, [after] * int((~is_before).sum()), color=BLUE, linewidth=1.4)
    top.axvline(moment, color=INK, linewidth=0.7)
    span = float(daily.abs().quantile(0.98))
    top.set_ylim(-span, span)
    top.set_xlim(daily.index.min(), window_end)
    top.text(
        daily.index.min() + pd.Timedelta(days=12),
        -span * 0.86,
        f"Mean, 365 days before: {before:+,.0f} MW",
        fontsize=7.5,
        color=INK,
        bbox=TEXT_BOX,
    )
    top.text(
        moment + pd.Timedelta(days=6),
        -span * 0.86,
        f"Mean, 180 days after: {after:+,.0f} MW",
        fontsize=7.5,
        color=INK,
        bbox=TEXT_BOX,
    )
    top.text(moment, span, f" Site start {start.isoformat()}", va="top", fontsize=7, color=INK)
    top.set_ylabel("Actual minus\nbaseline (MW)")
    _panel(
        top,
        "a",
        f"{BA_NAMES[ba]} used {estimate:,.0f} MW more than its weather baseline after the start",
    )

    bottom = figure.add_subplot(grid[1])
    y = stacked_dots(nulls, DOT_BIN_MW)
    bottom.scatter(nulls, y, s=16, color=DARK, edgecolor="white", linewidth=0.4)
    threshold = null_threshold(nulls)
    bottom.axvline(threshold, color=ORANGE, linewidth=0.9)
    bottom.text(threshold, y.max() + 1.4, " 95th percentile", fontsize=7, color=INK, va="top")
    bottom.scatter([estimate], [1], s=60, color=BLUE, edgecolor="white", linewidth=0.6, zorder=4)
    bottom.annotate(
        f"After the start: {estimate:+,.0f} MW",
        (estimate, 1),
        xytext=(estimate, y.max() * 0.7 + 1),
        fontsize=7.5,
        color=INK,
        ha="center",
        arrowprops={"arrowstyle": "-", "color": MUTED, "linewidth": 0.4},
    )
    bottom.set_ylim(0, y.max() + 1.6)
    bottom.set_yticks([])
    bottom.spines["left"].set_visible(False)
    bottom.set_xlabel("Step estimate, MW. Each grey dot is one window that ended before any site")
    beaten = int((nulls < estimate).sum())
    _panel(
        bottom,
        "b",
        f"The rise is larger than {beaten} of {len(nulls)} earlier windows, "
        f"so p = {rank_p(estimate, nulls):.3f}",
    )
    _save(figure, path)
