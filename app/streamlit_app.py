"""One page with the headline. It reads only app/data, which `atlas analyze early-extract` writes
from the frozen run, so the page can be hosted without the lake and cannot show a number the
pipeline did not produce."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

DATA = Path(__file__).parent / "data"
REPO = "https://github.com/VijayChamakuri/ai-power-atlas"
BLUE = "#2a78d6"
INK = "#1a1a1a"
GREY = "#8a8984"
ORANGE = "#eb6834"


@st.cache_data
def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    daily = pd.read_csv(DATA / "los_lunas_daily.csv", parse_dates=["date"])
    nulls = pd.read_csv(DATA / "los_lunas_nulls.csv")
    result = pd.read_csv(DATA / "los_lunas_result.csv").iloc[0]
    sites = pd.read_csv(DATA / "m1_sites.csv")
    return daily, nulls, result, sites


def residual_chart(daily: pd.DataFrame, start: pd.Timestamp) -> alt.LayerChart | alt.FacetChart:
    daily = daily.assign(period=(daily["date"] >= start).map({False: "before", True: "after"}))
    means = daily.groupby("period", as_index=False).agg(
        first=("date", "min"), last=("date", "max"), mean=("residual_mw", "mean")
    )
    base = alt.Chart(daily).encode(x=alt.X("date:T", title=None))
    line = base.mark_line(color=GREY, strokeWidth=0.8).encode(
        y=alt.Y("residual_mw:Q", title="Actual minus baseline (MW)"),
        tooltip=[
            alt.Tooltip("date:T", title="Day"),
            alt.Tooltip("residual_mw:Q", title="MW", format="+.0f"),
        ],
    )
    levels = (
        alt.Chart(means)
        .mark_rule(strokeWidth=2.5)
        .encode(
            x="first:T",
            x2="last:T",
            y="mean:Q",
            color=alt.Color(
                "period:N",
                scale=alt.Scale(domain=["before", "after"], range=[INK, BLUE]),
                legend=alt.Legend(title="Mean", orient="top"),
            ),
            tooltip=[alt.Tooltip("mean:Q", title="Mean MW", format="+.0f")],
        )
    )
    marker = (
        alt.Chart(pd.DataFrame({"date": [start]}))
        .mark_rule(color=INK, strokeDash=[4, 3])
        .encode(x="date:T")
    )
    return alt.layer(line, levels, marker, height=280)


def windows_chart(
    nulls: pd.DataFrame, estimate: float, threshold: float
) -> alt.LayerChart | alt.FacetChart:
    points = pd.concat(
        [
            nulls.assign(kind="Window before any site"),
            pd.DataFrame({"estimate_mw": [estimate], "kind": ["After the start"]}),
        ]
    )
    dots = (
        alt.Chart(points)
        .mark_circle(opacity=0.9)
        .encode(
            x=alt.X("estimate_mw:Q", title="Step estimate (MW)"),
            y=alt.Y("jitter:Q", axis=None),
            size=alt.condition(alt.datum.kind == "After the start", alt.value(160), alt.value(50)),
            color=alt.Color(
                "kind:N",
                scale=alt.Scale(
                    domain=["Window before any site", "After the start"], range=[GREY, BLUE]
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[alt.Tooltip("estimate_mw:Q", title="MW", format="+.1f"), "kind:N"],
        )
        .transform_calculate(jitter="random()")
    )
    cutoff = (
        alt.Chart(pd.DataFrame({"x": [threshold]}))
        .mark_rule(color=ORANGE)
        .encode(x="x:Q", tooltip=[alt.Tooltip("x:Q", title="95th percentile", format="+.0f")])
    )
    return alt.layer(dots, cutoff, height=160)


def main() -> None:
    st.set_page_config(page_title="AI Power Atlas", layout="centered")
    daily, nulls, result, sites = load()
    start = pd.Timestamp(result["start"])
    beaten = int((nulls["estimate_mw"] < result["estimate_mw"]).sum())

    st.title(
        f"After Meta Los Lunas started, New Mexico's grid used {result['estimate_mw']:.0f} MW "
        "more than weather explains"
    )
    st.markdown(
        "A pre-registered test on public hourly data from EIA-930. The method was committed to git "
        f"before the data existed. [Paper and code]({REPO}) · "
        f"[Analysis plan]({REPO}/blob/main/docs/analysis_plan.md)"
    )
    left, middle, right = st.columns(3)
    left.metric("Estimate", f"{result['estimate_mw']:+.0f} MW")
    middle.metric("90% interval", f"{result['low_mw']:.0f} to {result['high_mw']:.0f} MW")
    right.metric(
        "Rank p", f"{result['p']:.3f}", f"beats {beaten} of {len(nulls)}", "off", delta_arrow="off"
    )

    st.subheader(f"Demand above its weather baseline, before and after {start.date()}")
    st.altair_chart(residual_chart(daily, start), width="stretch")
    st.caption(
        "Each grey point is one day: actual demand minus a LightGBM baseline trained only on "
        "data that ends 365 days before the start. The estimate is the after mean minus the "
        "before mean."
    )

    st.subheader(f"The rise beats {beaten} of {len(nulls)} earlier windows")
    st.altair_chart(
        windows_chart(nulls, result["estimate_mw"], result["threshold_mw"]),
        width="stretch",
    )
    st.caption("Vertical position is random, only to keep dots apart.")

    st.subheader("Pre-registered checks")
    checks = pd.DataFrame(
        {
            "Check": [
                "Window 180 days before the start",
                "Other grids with no listed site",
                "Synthetic control gap",
                "Start moved 90 days earlier",
            ],
            "Value": [
                f"{result['lead_mw']:+.0f} MW",
                f"p = {result['other_grid_p']:.3f}",
                f"{result['synthetic_gap_mw']:+.0f} MW",
                f"{result['minus_90_mw']:+.0f} MW",
            ],
            "Rule": [
                f"Below {result['threshold_mw']:+.0f} MW",
                "0.10 or less",
                "Positive",
                "Reported only",
            ],
        }
    )
    st.dataframe(checks, hide_index=True, width="stretch")

    st.subheader("Why only this site: most grids are too large to see one campus")
    limits = sites.dropna(subset=["mde_mw"]).rename(
        columns={
            "site": "Site",
            "ba": "Grid",
            "power_mw": "Listed MW",
            "mde_mw": "Smallest visible step (MW)",
            "passes_go": "Passes",
        }
    )
    st.dataframe(
        limits[["Site", "Grid", "Listed MW", "Smallest visible step (MW)", "Passes"]].sort_values(
            "Smallest visible step (MW)"
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "From M1, data frozen 2026-10-31. Listed MW is Epoch AI's figure on that date. "
        "A site whose location falls in two grids appears once for each."
    )

    st.subheader("What this does not show")
    st.markdown(
        f"- A rise after the start does not prove the data center caused it.\n"
        f"- The interval tops out at {result['high_mw']:.0f} MW, below the "
        f"{result['expected_mw']:.0f} MW Epoch AI listed for that window, so the site may "
        "draw less.\n"
        f"- Moving the start 90 days earlier gives {result['minus_90_mw']:+.0f} MW, so the result "
        "leans on Epoch AI's start date.\n"
        f"- p = {result['p']:.3f} is the smallest value {len(nulls)} windows allow."
    )
    st.caption(
        "Data: EIA-930 (public domain), Open-Meteo (CC BY 4.0), Epoch AI Frontier Data Centers "
        "(CC BY 4.0). By Vijay Shankar Chamakuri."
    )


main()
