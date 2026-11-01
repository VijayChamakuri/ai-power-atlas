"""Turn Epoch's two files into one row per US site, by the rules in docs/analysis_plan.md."""

from datetime import date

import pandas as pd

from atlas.contracts.epoch import DATA_CENTERS, TIMELINES

BEHIND_METER_TERMS = (
    "turbine",
    "behind-the-meter",
    "behind the meter",
    "on-site power",
    "on-site generation",
    "power plant",
    "power generation",
    "fuel cell",
    "microgrid",
)


def matched_terms(notes: str) -> str:
    lowered = notes.lower()
    return ",".join(term for term in BEHIND_METER_TERMS if term in lowered)


def apply_flag_seeds(sites: pd.DataFrame, seeds: pd.DataFrame) -> pd.DataFrame:
    """Text search only finds what Epoch wrote. A cited seed can add a flag but never drop one."""
    unknown = set(seeds["site"]) - set(sites["site"])
    if unknown:
        raise ValueError(f"Flag seed names unknown sites: {sorted(unknown)}")
    flagged = sites.copy()
    seeded = flagged["site"].isin(seeds["site"])
    flagged.loc[seeded, "behind_meter_risk"] = True
    flagged.loc[seeded, "behind_meter_terms"] = (
        flagged.loc[seeded, "behind_meter_terms"].str.cat(
            ["hand_seed"] * int(seeded.sum()), sep=","
        )
    ).str.strip(",")
    return flagged


def build_sites(data_centers: pd.DataFrame, timelines: pd.DataFrame, freeze: date) -> pd.DataFrame:
    DATA_CENTERS.validate(data_centers)
    TIMELINES.validate(timelines)
    cutoff = freeze.isoformat()
    rows = []
    for _, row in data_centers[data_centers["Country"] == "United States"].iterrows():
        site = row["Name"]
        history = timelines[timelines["Data center"] == site].sort_values("Date", kind="stable")
        past = history[history["Date"] <= cutoff]
        powered = past[past["Power (MW)"] > 0]
        # Projected rows count for the flag: a planned plant is still a reason for doubt.
        notes = " ".join(history["Construction status"].fillna(""))
        terms = matched_terms(notes)
        address, sources = row["Address"], row["Selected Sources"]
        rows.append(
            {
                "site": site,
                "power_mw": float(past["Power (MW)"].iloc[-1]) if len(past) else 0.0,
                "first_date": powered["Date"].iloc[0] if len(powered) else None,
                "address": "" if pd.isna(address) else str(address),
                "behind_meter_risk": bool(terms),
                "behind_meter_terms": terms,
                "location_text": f"{notes} {'' if pd.isna(sources) else sources}",
                "confidence": "estimated",
            }
        )
    return pd.DataFrame(rows)
