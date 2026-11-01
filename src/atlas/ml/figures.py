"""Journal-style panels. The README caption carries the message, so each panel can carry the data.

Nothing here touches demand on or after a BA's first listed site. That is M2's job.
"""

import io
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shapefile
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from atlas.config import NULL_QUANTILE, POST_DAYS, POWER_QUANTILE, TRAIN_GAP_DAYS
from atlas.ml.detectability import detection_rate, mde_sensitivity, null_threshold

INK = "#1a1a1a"
MUTED = "#5f5f5a"
FAINT = "#b9b8b2"
RULE = "#e4e3de"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
DARK = "#4a4a46"
LAND = "#f2f1ed"
CARPET = LinearSegmentedColormap.from_list("carpet", ["#f7fbff", "#9ec5ea", "#2a78d6", "#08306b"])
STATUS_COLORS = {"passes": BLUE, "below_limit": DARK, "excluded": ORANGE, "no_number": FAINT}
STATUS_LABELS = {
    "passes": "Passes",
    "below_limit": "Below its limit",
    "excluded": "Excluded",
    "no_number": "No limit available",
}
LEADER = {"arrowstyle": "-", "color": MUTED, "linewidth": 0.4}
TEXT_BOX = {"facecolor": "white", "alpha": 0.82, "edgecolor": "none", "pad": 1.2}

plt.rcParams.update(
    {
        "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.titleweight": "regular",
        "axes.titlelocation": "left",
        "axes.titlecolor": INK,
        "axes.labelsize": 8,
        "axes.labelcolor": MUTED,
        "axes.edgecolor": MUTED,
        "axes.linewidth": 0.6,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "legend.frameon": False,
        "legend.fontsize": 7.5,
    }
)


def _save(figure: Figure, path: Path) -> None:
    figure.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.06)
    plt.close(figure)


def _panel(axes: Axes, letter: str, title: str) -> None:
    """Lowercase bold panel letters follow Nature's figure guide."""
    axes.annotate(
        letter,
        (0, 1),
        xycoords="axes fraction",
        xytext=(0, 6),
        textcoords="offset points",
        fontsize=10,
        fontweight="bold",
        color=INK,
    )
    axes.annotate(
        title,
        (0, 1),
        xycoords="axes fraction",
        xytext=(11, 6),
        textcoords="offset points",
        fontsize=8.5,
        color=INK,
    )


def short_name(site: str) -> str:
    for prefix in ("Anthropic-Amazon ", "OpenAI ", "Microsoft-Nebius ", "Microsoft "):
        site = site.replace(prefix, "")
    return site


def site_status(table: pd.DataFrame, sites: pd.DataFrame, site_bas: pd.DataFrame) -> pd.DataFrame:
    """One row per powered site. The order of the checks matches the go test."""
    located = site_bas.merge(sites[["site", "power_mw", "behind_meter_risk"]], on="site")
    passing = set(table[table["passes_go"]]["site"])
    with_limit = set(table[table["mde_mw"].notna()]["site"])

    def status(row: pd.Series) -> str:
        if row["site"] in passing:
            return "passes"
        if row["behind_meter_risk"] or "," in row["ba_codes"]:
            return "excluded"
        return "below_limit" if row["site"] in with_limit else "no_number"

    return located.assign(status=located.apply(status, axis=1))


def albers(longitude: np.ndarray, latitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Standard US Albers parallels. A plain lat-lon plot stretches the northern states."""
    lon, lat = np.radians(longitude), np.radians(latitude)
    first, second = np.radians(29.5), np.radians(45.5)
    origin_lat, origin_lon = np.radians(37.5), np.radians(-96.0)
    n = (np.sin(first) + np.sin(second)) / 2
    c = np.cos(first) ** 2 + 2 * n * np.sin(first)
    rho = np.sqrt(c - 2 * n * np.sin(lat)) / n
    rho_origin = np.sqrt(c - 2 * n * np.sin(origin_lat)) / n
    theta = n * (lon - origin_lon)
    return rho * np.sin(theta), rho_origin - rho * np.cos(theta)


def _state_rings(archive: bytes) -> list[np.ndarray]:
    with zipfile.ZipFile(io.BytesIO(archive)) as opened:
        reader = shapefile.Reader(
            shp=io.BytesIO(opened.read("cb_2023_us_state_20m.shp")),
            dbf=io.BytesIO(opened.read("cb_2023_us_state_20m.dbf")),
        )
        rings = []
        for record in reader.shapeRecords():
            if record.record["STUSPS"] in ("AK", "HI", "PR"):
                continue
            parts = [*record.shape.parts, len(record.shape.points)]
            points = np.array(record.shape.points)
            rings += [points[start:end] for start, end in zip(parts, parts[1:], strict=False)]
    return rings


def _bubble(power_mw: np.ndarray) -> np.ndarray:
    return power_mw * 0.17 + 5


def site_map(status: pd.DataFrame, states_zip: bytes, path: Path) -> None:
    figure = plt.figure(figsize=(7.4, 5.6))
    grid = figure.add_gridspec(2, 1, height_ratios=[5.2, 1], hspace=0.1)
    axes = figure.add_subplot(grid[0])
    for ring in _state_rings(states_zip):
        x, y = albers(ring[:, 0], ring[:, 1])
        axes.fill(x, y, facecolor=LAND, edgecolor="#d4d3cd", linewidth=0.4)
    for key in ("no_number", "excluded", "below_limit", "passes"):
        chosen = status[status["status"] == key].sort_values("power_mw", ascending=False)
        x, y = albers(chosen["longitude"].to_numpy(), chosen["latitude"].to_numpy())
        axes.scatter(
            x,
            y,
            s=_bubble(chosen["power_mw"].to_numpy()),
            color=STATUS_COLORS[key],
            alpha=0.88,
            edgecolor="white",
            linewidth=0.5,
            zorder=4 if key == "passes" else 3,
        )
    labels = {
        "Meta Kuna": (0, -15),
        "Meta Los Lunas": (0, -15),
        "Anthropic-Amazon New Carlisle": (-20, 25),
        "Colossus 2": (-6, 27),
        "OpenAI Stargate Abilene": (-42, -24),
        "Microsoft Fairwater Atlanta": (40, -20),
        "Meta Prometheus": (24, 28),
        "Google Pryor (North)": (-54, 4),
    }
    for site, offset in labels.items():
        row = status[status["site"] == site].iloc[0]
        x, y = albers(np.array([row["longitude"]]), np.array([row["latitude"]]))
        axes.annotate(
            f"{short_name(site)}\n{row['power_mw']:,.0f} MW",
            (x[0], y[0]),
            xytext=offset,
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=7,
            color=INK,
            linespacing=1.05,
            arrowprops=LEADER,
            zorder=5,
        )
    size_handles = [
        Line2D(
            [],
            [],
            marker="o",
            color="none",
            markerfacecolor="none",
            markeredgecolor=MUTED,
            markeredgewidth=0.6,
            markersize=float(np.sqrt(_bubble(np.array([value]))[0])),
            label=f"{value:,} MW",
        )
        for value in (100, 500, 1000)
    ]
    axes.legend(
        handles=size_handles,
        loc="lower left",
        labelspacing=1.1,
        title="Epoch power",
        title_fontsize=7.5,
        handletextpad=1.1,
    )
    axes.set_aspect("equal")
    axes.axis("off")
    _panel(axes, "a", "Where the listed sites are, and how each fared in the test")

    bars = figure.add_subplot(grid[1])
    order = ["passes", "below_limit", "excluded", "no_number"]
    counts = status["status"].value_counts().reindex(order).fillna(0)
    power = status.groupby("status")["power_mw"].sum().reindex(order).fillna(0)
    for level, values, unit in ((1, counts, "sites"), (0, power, "MW")):
        left = 0.0
        for key in order:
            share = float(values[key] / values.sum() * 100)
            bars.barh(
                level,
                share,
                left=left,
                height=0.62,
                color=STATUS_COLORS[key],
                edgecolor="white",
                linewidth=1,
            )
            text = f"{values[key]:,.0f}" if share >= 2.4 else ""
            bars.text(
                left + share / 2,
                level,
                text,
                ha="center",
                va="center",
                fontsize=7,
                color=INK if key == "no_number" else "white",
            )
            left += share
        bars.text(-1, level, f"{values.sum():,.0f} {unit}", ha="right", va="center", color=INK)
    bars.set_xlim(0, 100)
    bars.set_ylim(-0.5, 1.5)
    bars.axis("off")
    handles = [
        Line2D(
            [],
            [],
            marker="s",
            color="none",
            markerfacecolor=STATUS_COLORS[key],
            markersize=6,
            markeredgecolor="none",
            label=STATUS_LABELS[key],
        )
        for key in order
    ]
    bars.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.02),
        ncol=4,
        handletextpad=0.2,
        columnspacing=1.2,
    )
    _panel(bars, "b", "Share of sites and share of power in each outcome")
    _save(figure, path)


def _carpet(axes: Axes, demand: pd.Series, timezone: str) -> Any:
    local = pd.DatetimeIndex(demand.index).tz_convert(timezone)
    frame = pd.DataFrame(
        {"value": demand.to_numpy(), "day": local.floor("D").tz_localize(None), "hour": local.hour}
    )
    grid = frame.pivot_table(index="hour", columns="day", values="value", aggfunc="mean")
    percent = grid / float(np.nanmedian(grid.to_numpy())) * 100
    columns: Any = percent.columns
    days = mdates.date2num(columns)  # type: ignore[no-untyped-call]
    image = axes.imshow(
        percent.to_numpy(),
        aspect="auto",
        origin="lower",
        cmap=CARPET,
        vmin=60,
        vmax=170,
        extent=(float(days[0]), float(days[-1]), 0, 24),
        interpolation="nearest",
    )
    axes.xaxis_date()
    axes.xaxis.set_major_locator(mdates.YearLocator())  # type: ignore[no-untyped-call]
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))  # type: ignore[no-untyped-call]
    axes.set_yticks([0, 6, 12, 18, 24], ["00", "06", "12", "18", "24"])
    axes.set_ylabel("Local hour")
    return image


def _weather_curve(axes: Axes, demand: pd.Series, temperature: pd.Series) -> None:
    daily = pd.DataFrame({"demand": demand, "temperature": temperature}).dropna()
    daily = daily.groupby(pd.DatetimeIndex(daily.index).floor("D")).mean()
    axes.scatter(daily["temperature"], daily["demand"], s=2.2, color=BLUE, alpha=0.22, linewidth=0)
    bins = (daily["temperature"] // 5) * 5 + 2.5
    median = daily.groupby(bins)["demand"].agg(["median", "count"])
    median = median[median["count"] >= 10]
    axes.plot(median.index, median["median"], color=INK, linewidth=1.1)
    mild = float(daily[daily["temperature"].between(55, 65)]["demand"].median())
    hottest = daily["temperature"] >= daily["temperature"].quantile(0.95)
    hot = float(daily[hottest]["demand"].median())
    axes.axhline(mild, color=MUTED, linewidth=0.5, linestyle=(0, (3, 3)))
    axes.annotate(
        f"Hottest 5% of days:\n+{hot - mild:,.0f} MW vs 55-65 F days",
        (float(daily["temperature"].quantile(0.97)), hot),
        xytext=(-58, 2),
        textcoords="offset points",
        ha="center",
        fontsize=7,
        color=INK,
        arrowprops=LEADER,
    )
    axes.set_xlabel("Population-weighted temperature (F)")
    axes.set_ylabel("Daily mean demand (MW)")
    axes.yaxis.set_major_formatter(lambda value, _: f"{value:,.0f}")


def demand_anatomy(frames: list[dict[str, Any]], path: Path) -> None:
    """Each frame holds demand already cut to before that BA's first listed site."""
    figure = plt.figure(figsize=(8.2, 4.5))
    grid = figure.add_gridspec(2, 4, width_ratios=[1.45, 0.035, 0.42, 1], hspace=0.42, wspace=0.04)
    letters = iter("abcd")
    image: Any = None
    carpets = []
    for row, item in enumerate(frames):
        ba = item["ba"]
        carpet_axes = figure.add_subplot(grid[row, 0])
        carpets.append(carpet_axes)
        start = item["demand"].index.max() - pd.Timedelta(days=1096)
        image = _carpet(
            carpet_axes, item["demand"][item["demand"].index >= start], item["timezone"]
        )
        _panel(carpet_axes, next(letters), f"{ba}: every hour, last 3 years before its first site")
        curve_axes = figure.add_subplot(grid[row, 3])
        _weather_curve(curve_axes, item["demand"], item["temperature"])
        _panel(curve_axes, next(letters), f"{ba}: each dot is a day, line is the median")
    bar = figure.colorbar(image, cax=figure.add_subplot(grid[:, 1]))
    bar.set_label("Demand, % of median hour", fontsize=7.5, color=MUTED, labelpad=1)
    bar.ax.tick_params(labelsize=7, length=2)
    _save(figure, path)


def worked_example(
    ba: str, actual: pd.Series, predicted: pd.Series, t: date, series: pd.DataFrame, path: Path
) -> None:
    # Matplotlib accepts dates in these calls, though its type stubs only declare float.
    moment: Any = pd.Timestamp(t, tz="UTC")
    train_end: Any = moment - pd.Timedelta(days=TRAIN_GAP_DAYS)
    window_end: Any = moment + pd.Timedelta(days=POST_DAYS)
    index = pd.DatetimeIndex(actual.index).floor("D")
    days = pd.DataFrame(
        {"actual": actual.groupby(index).mean(), "predicted": predicted.groupby(index).mean()}
    )
    smooth = days.rolling(7, center=True, min_periods=4).mean()
    residual = days["actual"] - days["predicted"]
    is_before = residual.index < moment
    before = float(residual[is_before].mean())
    after = float(residual[~is_before].mean())

    figure = plt.figure(figsize=(7.4, 6.3))
    grid = figure.add_gridspec(3, 1, height_ratios=[1.45, 1, 1.1], hspace=0.42)
    top = figure.add_subplot(grid[0])
    top.axvspan(moment, window_end, color=BLUE, alpha=0.06, linewidth=0)
    top.plot(smooth.index, smooth["actual"], color=INK, linewidth=1.1)
    top.plot(smooth.index, smooth["predicted"], color=ORANGE, linewidth=1.1)
    peak_day: Any = smooth["predicted"].idxmax()
    top.annotate(
        "Orange: baseline, from weather\nand calendar alone\nBlack: actual demand",
        (peak_day, float(smooth["predicted"].max())),
        xytext=(moment + pd.Timedelta(days=9), 2880),
        fontsize=7.5,
        color=INK,
        va="top",
        arrowprops=LEADER,
    )
    top.set_ylabel("Seven-day mean (MW)")
    top.yaxis.set_major_formatter(lambda value, _: f"{value:,.0f}")
    y_top = top.get_ylim()[1]
    top.text(train_end, y_top, " Training stopped here", va="top", fontsize=7, color=MUTED)
    top.text(moment, y_top, " Test date t", va="top", fontsize=7, color=INK)
    _panel(top, "a", f"{ba}: the model predicts 545 days it has never seen")

    middle = figure.add_subplot(grid[1], sharex=top)
    middle.axvspan(moment, window_end, color=BLUE, alpha=0.06, linewidth=0)
    middle.axhline(0, color=FAINT, linewidth=0.6)
    middle.plot(residual.index, residual, color=FAINT, linewidth=0.5)
    middle.plot(
        residual[is_before].index, [before] * int(is_before.sum()), color=INK, linewidth=1.4
    )
    middle.plot(
        residual[~is_before].index, [after] * int((~is_before).sum()), color=BLUE, linewidth=1.4
    )
    span = float(residual.abs().quantile(0.98))
    middle.set_ylim(-span, span)
    middle.text(
        train_end + pd.Timedelta(days=12),
        -span * 0.86,
        f"Mean error, 365 days before: {before:+,.0f} MW",
        fontsize=7.5,
        color=INK,
        bbox=TEXT_BOX,
    )
    middle.text(
        moment + pd.Timedelta(days=6),
        -span * 0.86,
        f"Mean error, 180 days after: {after:+,.0f} MW",
        fontsize=7.5,
        color=INK,
        bbox=TEXT_BOX,
    )
    middle.set_ylabel("Actual minus\nbaseline (MW)")
    _panel(
        middle,
        "b",
        f"Step estimate e(t) = after minus before = {after - before:+,.0f} MW, "
        "with no step to find",
    )
    for axes in (top, middle):
        axes.axvline(moment, color=INK, linewidth=0.7)
        axes.axvline(train_end, color=MUTED, linewidth=0.5, linestyle=(0, (3, 3)))
        axes.set_xlim(train_end, window_end)

    bottom = figure.add_subplot(grid[2])
    values = series["estimate_mw"].to_numpy()
    threshold = null_threshold(values)
    low = float(np.quantile(values, POWER_QUANTILE))
    bottom.axhspan(low, threshold, color=ORANGE, alpha=0.1, linewidth=0)
    bottom.axhline(threshold, color=ORANGE, linewidth=0.9)
    bottom.axhline(low, color=ORANGE, linewidth=0.5, linestyle=(0, (3, 3)))
    bottom.axhline(0, color=FAINT, linewidth=0.6)
    dates: Any = series["date"]
    bottom.plot(
        dates,
        values,
        color=DARK,
        linewidth=0.8,
        marker="o",
        markersize=2.6,
        markerfacecolor=DARK,
        markeredgewidth=0,
    )
    last: Any = dates.iloc[-1]
    callout_x: Any = pd.Timestamp("2024-12-01")
    bottom.scatter(
        [last], [values[-1]], s=30, color=BLUE, zorder=4, edgecolor="white", linewidth=0.5
    )
    bottom.annotate(
        f"The window in a and b:\n{values[-1]:+,.0f} MW",
        (last, values[-1]),
        xytext=(callout_x, -44),
        fontsize=7,
        color=INK,
        ha="center",
        arrowprops=LEADER,
    )
    label_x: Any = pd.Timestamp("2022-08-15")
    bottom.text(
        label_x,
        threshold + 3,
        f"95th percentile: {threshold:+,.0f} MW, the detection threshold",
        fontsize=7,
        color=INK,
        va="bottom",
    )
    low_x: Any = pd.Timestamp("2024-09-15")
    bottom.text(
        low_x, low + 3, f"20th percentile: {low:+,.0f} MW", fontsize=7, color=INK, va="bottom"
    )
    bottom.set_ylabel("Step estimate e(t), MW")
    _panel(
        bottom,
        "c",
        "Repeating it every 30 days gives the noise. "
        f"The band, {threshold - low:,.0f} MW, is the limit",
    )
    _save(figure, path)


def noise_panels(
    series: pd.DataFrame, limits: pd.DataFrame, first_sites: dict[str, date], path: Path
) -> None:
    """One shared y scale in percent of peak, so grids of very different size compare directly."""
    usable = limits.dropna(subset=["mde_mw"])
    order = usable.assign(percent=usable["mde_mw"] / usable["peak_mw"] * 100).sort_values("percent")
    figure, grid = plt.subplots(3, 4, figsize=(7.4, 5.2), sharex=True, sharey=True)
    flat = grid.ravel()
    x_start: Any = pd.Timestamp("2021-10-01")
    x_end: Any = pd.Timestamp("2026-10-31")
    ticks: Any = [pd.Timestamp(f"{year}-01-01") for year in (2022, 2024, 2026)]
    for axes, row in zip(flat, order.to_dict("records"), strict=False):
        ba = str(row["ba"])
        chosen = series[series["ba"] == ba]
        percent = chosen["estimate_mw"].to_numpy() / row["peak_mw"] * 100
        threshold = float(np.quantile(percent, NULL_QUANTILE))
        low = float(np.quantile(percent, POWER_QUANTILE))
        axes.axhspan(low, threshold, color=ORANGE, alpha=0.13, linewidth=0)
        axes.axhline(0, color=FAINT, linewidth=0.5)
        dates: Any = chosen["date"]
        axes.plot(dates, percent, color=DARK, linewidth=0.8)
        site: Any = pd.Timestamp(first_sites[ba])
        axes.axvline(site, color=BLUE, linewidth=0.8)
        axes.set_xlim(x_start, x_end)
        axes.annotate(
            ba,
            (0, 1),
            xycoords="axes fraction",
            xytext=(0, 4),
            textcoords="offset points",
            fontsize=8,
            fontweight="bold",
            color=INK,
        )
        axes.annotate(
            f"{row['percent']:.1f}%, {row['mde_mw']:,.0f} MW",
            (1, 1),
            xycoords="axes fraction",
            xytext=(0, 4),
            textcoords="offset points",
            fontsize=7,
            color=INK,
            ha="right",
        )
        axes.set_xticks(ticks, ["2022", "2024", "2026"])
    note = flat[len(order)]
    note.axis("off")
    note.text(
        0.04,
        0.5,
        "How to read\n\nLine: step estimate at each\ntest date, % of peak.\n"
        "Band: the detection limit.\nBlue line: first listed site.\n"
        "Later dates would include\nreal site load, so none\nare computed.",
        transform=note.transAxes,
        fontsize=7,
        color=INK,
        va="center",
        linespacing=1.3,
    )
    for axes in flat[len(order) + 1 :]:
        axes.axis("off")
    figure.supylabel("Step estimate e(t), % of 12-month peak", fontsize=8, color=MUTED, x=0.05)
    figure.subplots_adjust(wspace=0.09, hspace=0.2)
    _save(figure, path)


def power_curves(
    estimates: pd.DataFrame, limits: pd.DataFrame, table: pd.DataFrame, path: Path
) -> None:
    figure = plt.figure(figsize=(7.4, 3.3))
    grid = figure.add_gridspec(1, 3, width_ratios=[1.5, 1, 1], wspace=0.28)
    left = figure.add_subplot(grid[0])
    highlight = {"PJM": INK, "IPCO": BLUE, "PNM": ORANGE}
    usable = limits.dropna(subset=["mde_mw"])
    steps = np.linspace(0, 8, 321)
    for row in usable.to_dict("records"):
        ba = str(row["ba"])
        values = estimates[estimates["ba"] == ba]["estimate_mw"].to_numpy()
        rates = np.array([detection_rate(values, s / 100 * row["peak_mw"]) * 100 for s in steps])
        special = ba in highlight
        left.plot(
            steps,
            rates,
            color=highlight.get(ba, FAINT),
            linewidth=1.3 if special else 0.7,
            zorder=3 if special else 2,
            drawstyle="steps-post",
        )
        if special:
            target, label_at = {
                "IPCO": (70, (0.35, 76)),
                "PNM": (58, (3.5, 52)),
                "PJM": (30, (3.5, 24)),
            }[ba]
            position = int(np.searchsorted(rates, target))
            left.annotate(
                ba,
                (steps[position], rates[position]),
                xytext=label_at,
                fontsize=7.5,
                fontweight="bold",
                color=INK,
                va="center",
                arrowprops=LEADER,
            )
    for level, text in ((80, "80% power"), (5, "5% false alarms")):
        left.axhline(level, color=MUTED, linewidth=0.5, linestyle=(0, (3, 3)))
        left.text(8, level + 1.5, text, ha="right", fontsize=7, color=MUTED)
    left.set_xlabel("Step size, % of 12-month peak")
    left.set_ylabel("Chance the step is detected (%)")
    left.set_xlim(0, 8)
    left.set_ylim(0, 102)
    _panel(left, "a", "All 11 series. Gray: the other 8")

    panels = (
        (1, "IPCO", ["Meta Kuna"], "b", 300.0, (193.0, 22.0)),
        (2, "PJM", ["Anthropic-Amazon New Carlisle"], "c", 6000.0, (1420.0, 11.0)),
    )
    for slot, ba, chosen_sites, letter, x_max, place in panels:
        axes = figure.add_subplot(grid[slot])
        values = estimates[estimates["ba"] == ba]["estimate_mw"].to_numpy()
        grid_mw = np.linspace(0, x_max, 301)
        rates = np.array([detection_rate(values, step) * 100 for step in grid_mw])
        axes.plot(grid_mw, rates, color=DARK, linewidth=1, drawstyle="steps-post")
        for site in chosen_sites:
            power = float(table[table["site"] == site]["power_mw"].iloc[0])
            rate = detection_rate(values, power) * 100
            axes.plot([power, power], [0, rate], color=BLUE, linewidth=0.8)
            axes.scatter(
                [power], [rate], s=18, color=BLUE, zorder=4, edgecolor="white", linewidth=0.4
            )
            axes.text(
                *place,
                f"{short_name(site)}\n{power:,.0f} MW: {rate:.0f}%",
                fontsize=7,
                color=INK,
                linespacing=1.05,
                ha="right" if place[0] < power else "left",
            )
        axes.axhline(80, color=MUTED, linewidth=0.5, linestyle=(0, (3, 3)))
        axes.set_xlim(0, x_max)
        axes.set_ylim(0, 102)
        axes.set_xlabel("Step size (MW)")
        axes.xaxis.set_major_formatter(lambda value, _: f"{value:,.0f}")
        _panel(axes, letter, f"{ba}: one real site")
    _save(figure, path)


def _forest_text(axes: Axes, x: float, y: float, text: str, **style: Any) -> None:
    style.setdefault("fontsize", 7)
    style.setdefault("color", INK)
    axes.text(x, y, text, transform=axes.get_yaxis_transform(), va="center", **style)


def forest_plot(table: pd.DataFrame, estimates: pd.DataFrame, path: Path) -> None:
    rows = table[table["mde_mw"].notna()].copy()
    rows["ratio"] = rows["power_mw"] / rows["mde_mw"]
    rows["best"] = rows.groupby("ba")["ratio"].transform("max")
    rows = rows.sort_values(["best", "ba", "ratio"], ascending=[False, True, False])

    height = len(rows) * 0.158 + rows["ba"].nunique() * 0.2 + 0.7
    figure, axes = plt.subplots(figsize=(7.4, height))
    figure.subplots_adjust(left=0.33, right=0.74, bottom=0.078, top=0.995)
    position = 0.0
    edge_left, edge_right = 0.008, 8.0
    current = ""
    for row in rows.to_dict("records"):
        if row["ba"] != current:
            current = str(row["ba"])
            position -= 0.55
            _forest_text(axes, -0.82, position, current, fontweight="bold", fontsize=7.5)
            _forest_text(axes, -0.65, position, f"limit {row['mde_mw']:,.0f} MW", color=MUTED)
            position -= 1
        values = estimates[estimates["ba"] == row["ba"]]["estimate_mw"].to_numpy()
        check = mde_sensitivity(values)
        low, high = min(check.values()), max(check.values())
        passes = bool(row["passes_go"])
        flagged = bool(row["behind_meter_risk"])
        overlap = bool(row["overlap"])
        color = BLUE if passes else (ORANGE if flagged or overlap else DARK)
        axes.plot(
            [max(row["power_mw"] / high, edge_left), min(row["power_mw"] / low, edge_right)],
            [position, position],
            color=color,
            linewidth=0.8,
            alpha=0.75,
            zorder=2,
        )
        axes.scatter(
            row["ratio"],
            position,
            s=22 if passes else 13,
            marker="D" if flagged else ("s" if overlap else "o"),
            color=color,
            zorder=3,
            edgecolor="white",
            linewidth=0.35,
        )
        weight = "bold" if passes else "normal"
        _forest_text(axes, -0.8, position, short_name(str(row["site"])), fontweight=weight)
        _forest_text(axes, -0.03, position, f"{row['power_mw']:,.0f}", ha="right")
        _forest_text(axes, 1.09, position, f"{row['ratio']:.2f}", ha="right")
        rate = detection_rate(values, float(row["power_mw"])) * 100
        _forest_text(axes, 1.27, position, f"{rate:.0f}%", ha="right")
        verdict = (
            "Passes" if passes else ("On-site" if flagged else ("Overlap" if overlap else "Below"))
        )
        _forest_text(axes, 1.31, position, verdict, fontweight=weight)
        position -= 1
    axes.axvline(1, color=INK, linewidth=0.8, zorder=1)
    axes.set_xscale("log")
    axes.set_xlim(edge_left, edge_right)
    axes.set_ylim(position - 0.1, 2.3)
    axes.set_yticks([])
    axes.spines["left"].set_visible(False)
    axes.set_xticks([0.01, 0.1, 0.5, 1, 2, 5], ["0.01", "0.1", "0.5", "1", "2", "5"])
    axes.minorticks_off()
    axes.set_xlabel("Site power ÷ BA detection limit (log scale)")
    axes.grid(axis="x", color=RULE, linewidth=0.5, zorder=0)
    _forest_text(axes, -0.82, 1.0, "Site", color=MUTED, fontsize=7.5)
    _forest_text(axes, -0.03, 1.0, "MW", color=MUTED, fontsize=7.5, ha="right")
    _forest_text(axes, 1.09, 1.0, "Ratio", color=MUTED, fontsize=7.5, ha="right")
    _forest_text(axes, 1.27, 1.0, "Seen*", color=MUTED, fontsize=7.5, ha="right")
    _forest_text(axes, 1.31, 1.0, "Result", color=MUTED, fontsize=7.5)
    axes.text(0.93, 1.0, "← too small to see", ha="right", fontsize=7.5, color=INK, va="center")
    axes.text(1.07, 1.0, "large enough →", ha="left", fontsize=7.5, color=INK, va="center")
    handles = [
        Line2D([], [], marker="o", color="none", markerfacecolor=BLUE, markeredgecolor="none",
               markersize=4.5, label="Passes"),
        Line2D([], [], marker="o", color="none", markerfacecolor=DARK, markeredgecolor="none",
               markersize=4.5, label="Below limit"),
        Line2D([], [], marker="D", color="none", markerfacecolor=ORANGE, markeredgecolor="none",
               markersize=4, label="On-site power flag"),
        Line2D([], [], marker="s", color="none", markerfacecolor=ORANGE, markeredgecolor="none",
               markersize=4, label="Overlapping BA areas"),
        Line2D([], [], color=DARK, linewidth=0.8, label="Range on parts of the history"),
    ]  # fmt: skip
    figure.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.005),
        ncol=5,
        handletextpad=0.4,
        columnspacing=1.0,
    )
    _save(figure, path)


def grid_context(limits: pd.DataFrame, candidates: pd.DataFrame, path: Path) -> None:
    figure = plt.figure(figsize=(7.4, 4.1))
    grid = figure.add_gridspec(1, 2, width_ratios=[1, 1.25], wspace=0.28)
    left = figure.add_subplot(grid[0])
    rows = candidates.sort_values("share")
    positions = np.arange(len(rows))
    left.hlines(
        positions, rows["share"].min() * 100 * 0.8, rows["share"] * 100, color=RULE, linewidth=0.8
    )
    colors = [BLUE if flag else FAINT for flag in rows["candidate"]]
    left.scatter(rows["share"] * 100, positions, s=17, color=colors, zorder=3)
    left.axvline(2, color=INK, linewidth=0.7)
    left.text(2.1, 0.0, "2% rule", fontsize=7, color=INK, va="center")
    left.set_yticks(positions, rows["ba"])
    left.tick_params(axis="y", length=0, labelsize=7)
    left.set_xscale("log")
    left.set_xticks([1, 2, 5, 10, 30], ["1", "2", "5", "10", "30"])
    left.minorticks_off()
    left.set_xlabel("Listed site power, % of 12-month peak")
    wacm = list(rows["ba"]).index("WACM")
    left.annotate(
        "Data ends before\nits only site",
        (float(rows.iloc[wacm]["share"]) * 100, wacm),
        xytext=(32, -3),
        textcoords="offset points",
        fontsize=7,
        color=INK,
        va="center",
        arrowprops=LEADER,
    )
    qualified = int(rows["candidate"].sum())
    _panel(left, "a", f"Which grids qualified: {qualified} of {len(rows)} (blue)")

    right = figure.add_subplot(grid[1])
    usable = limits.dropna(subset=["mde_mw"])
    peak_range = np.array([1500, 300000.0])
    for share, label, x in ((0.01, "1% of peak", 120000), (0.02, "2%", 17000), (0.05, "5%", 17000)):
        right.plot(peak_range, peak_range * share, color=FAINT, linewidth=0.6, zorder=1)
        right.text(
            x,
            x * share,
            label,
            fontsize=7,
            color=MUTED,
            ha="center",
            va="center",
            bbox=TEXT_BOX,
        )
    secondary = usable["ba"] == "AEP"
    right.scatter(
        usable[~secondary]["peak_mw"], usable[~secondary]["mde_mw"], s=19, color=DARK, zorder=3
    )
    right.scatter(
        usable[secondary]["peak_mw"],
        usable[secondary]["mde_mw"],
        s=21,
        marker="D",
        color=ORANGE,
        zorder=3,
    )
    offsets = {
        "PACW": (-5, 5),
        "PNM": (-5, 5),
        "NEVP": (-3, 6),
        "SOCO": (-5, 6),
        "ERCO": (-4, 6),
        "PJM": (-5, 6),
    }
    for row in usable.to_dict("records"):
        offset = offsets.get(str(row["ba"]), (6, -3))
        right.annotate(
            f"{row['ba']} {row['mde_mw']:,.0f}",
            (row["peak_mw"], row["mde_mw"]),
            xytext=offset,
            textcoords="offset points",
            fontsize=7,
            color=INK,
            ha="right" if offset[0] < 0 else "left",
        )
    right.set_xscale("log")
    right.set_yscale("log")
    right.set_xlim(1500, 300000)
    right.set_ylim(20, 8000)
    right.set_xticks(
        [2000, 5000, 10000, 50000, 200000], ["2,000", "5,000", "10,000", "50,000", "200,000"]
    )
    right.set_yticks([20, 50, 100, 500, 1000, 5000], ["20", "50", "100", "500", "1,000", "5,000"])
    right.minorticks_off()
    right.set_xlabel("12-month peak demand (MW)")
    right.set_ylabel("Detection limit (MW)")
    _panel(right, "b", "Bigger grids need bigger steps, at a similar share")
    _save(figure, path)


def accuracy(scores: pd.DataFrame, limits: pd.DataFrame, path: Path) -> None:
    rows = scores.merge(limits[["ba", "peak_mw"]], on="ba")
    model = rows[rows["benchmark"] == "model"].sort_values("mape", ascending=False)
    order = {ba: position for position, ba in enumerate(model["ba"])}
    style = {
        "seasonal_naive": (FAINT, "s", "Same hour last week"),
        "eia_day_ahead": (ORANGE, "D", "EIA day-ahead forecast"),
        "model": (BLUE, "o", "This study's baseline"),
    }
    metrics = (
        ("mape", False, "MAPE (%)", "Average hour"),
        ("rmse", True, "RMSE, % of peak", "Penalizes big misses"),
        ("peak_hour_mae", True, "Peak-hour error, % of peak", "Each day's highest hour"),
    )
    figure, grid = plt.subplots(1, 3, figsize=(7.4, 3.6), sharey=True)
    for axes, (metric, scaled, label, title), letter in zip(grid, metrics, "abc", strict=True):
        for key, (color, marker, name) in style.items():
            chosen = rows[rows["benchmark"] == key].dropna(subset=[metric])
            values = chosen[metric] / chosen["peak_mw"] * 100 if scaled else chosen[metric]
            axes.scatter(
                values,
                chosen["ba"].map(order),
                s=17,
                color=color,
                marker=marker,
                zorder=3 if key == "model" else 2,
                edgecolor="white",
                linewidth=0.3,
                label=name,
            )
        axes.set_xlim(0, 12)
        axes.set_xticks([0, 2, 4, 6, 8, 10, 12])
        axes.set_xlabel(label)
        axes.grid(axis="y", color=RULE, linewidth=0.5, zorder=0)
        axes.tick_params(axis="y", length=0)
        _panel(axes, letter, title)
    grid[0].set_yticks(list(order.values()), list(order.keys()))
    handles, names = grid[0].get_legend_handles_labels()
    figure.legend(
        handles,
        names,
        loc="lower center",
        ncol=3,
        bbox_to_anchor=(0.5, -0.1),
        handletextpad=0.2,
        markerscale=1.3,
    )
    _save(figure, path)
