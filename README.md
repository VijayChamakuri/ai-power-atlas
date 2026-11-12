# AI Power Atlas

[![CI](https://img.shields.io/github/actions/workflow/status/VijayChamakuri/ai-power-atlas/ci.yml?branch=main&label=ci)](https://github.com/VijayChamakuri/ai-power-atlas/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB)](https://www.python.org/downloads/release/python-3120/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Vijay Shankar Chamakuri

I test whether one AI data center is large enough to see in a US grid operator's hourly electricity demand, and whether demand jumped after one campus was listed as starting.

The demand series are the US Energy Information Administration's Form 930 (EIA-930). Campus sizes and dates are from Epoch AI, and weather is from Open-Meteo. The detectability inputs are frozen on 31 October 2026.

On Public Service Company of New Mexico (PNM), demand in the 180 days after Meta's Los Lunas campus was listed as starting sat 64 megawatts (MW) above a weather baseline, higher than all 45 earlier windows on that grid.

<p align="center"><img src="docs/figures/fig9_los_lunas.png" width="720" alt="PNM demand minus its weather baseline. The year before 1 March 2026 averages -30 MW and the 180 days after average +34 MW. The lower panel shows 45 earlier step estimates, all below +64 MW, with rank p = 0.022."></p>

Early event study, from the snapshot frozen on 1 November 2026. The detectability freeze is the day before. The flat lines are the mean residual before the listed start (-30 MW) and after it (+34 MW). The estimate is the difference, rounded to the nearest MW, which is also how the chart labels it.

| | Los Lunas on PNM |
|---|---|
| Step estimate | +64 MW |
| 90% interval | +13 to +102 MW |
| Pre-site windows beaten | 45 of 45 |
| Rank p | 0.022 |
| Epoch power for this window | 114 MW |

The baseline is the demand predicted from the calendar and from temperature and humidity. The step estimate is the average miss in the 180 days after a date, minus the average miss in the year before it. Rank p is where that estimate sits among windows that ended before any listed campus on the same grid.

The rise clears the comparison that was committed before this snapshot. It is still smaller than the 114 MW Epoch listed for this window, and a higher residual does not show that the campus caused it. I set the final label only when the second site, Meta Kuna on Idaho Power, is scored, which cannot happen before 15 December 2026. Stored values and the other checks are in [docs/RESULTS.md](docs/RESULTS.md). The working paper is [docs/paper.md](docs/paper.md) ([PDF](docs/paper.pdf)).

## How it works

### Which campuses are even testable

A balancing authority (BA) is the organization that matches supply and demand on one part of the grid. I keep a BA when its listed campuses are at least 2% of its peak hour, and I keep a campus only if it sits in one grid boundary, has no on-site generation flag, and is at least as large as that grid's detection limit. Two of 60 sites pass, holding 345 of 15,835 MW: Meta Kuna, 198 MW against a 98 MW limit on Idaho Power, and Meta Los Lunas, 147 MW on the 31 October 2026 list against a 77 MW limit on PNM. The event study uses 114 MW for Los Lunas, Epoch's figure for the 1 March 2026 window, not that 147 MW ([`select_candidates`](src/atlas/ml/candidates.py), [`go_test`](src/atlas/ml/detectability.py)).

### Weather baseline

I want the jump, not the weather. A straight line is fit on the training window, [LightGBM](https://lightgbm.readthedocs.io/) fits what is left, and the line is added back, because a tree cannot extrapolate a trend and a missing trend would look like new load. The features are local hour, weekday, month, a US federal holiday, temperature, humidity, and heating and cooling degrees from a 65 F base, with no lagged demand, and hours at or below zero or above three times the median are dropped. Settings are in [docs/METHODOLOGY.md](docs/METHODOLOGY.md), and the fit is [`src/atlas/ml/baseline.py`](src/atlas/ml/baseline.py).

### Detection limit

Test dates fall every 30 days. The model trains on data that ends a year earlier, scores the next 545 days, and the step estimate (`PRE_DAYS` is 365, `POST_DAYS` is 180) is:

```python
def step_estimate(daily_residuals: pd.Series, t: date) -> float:
    """Mean residual in the 180 days after t, minus the mean in the 365 days before it."""
    moment = pd.Timestamp(t, tz="UTC")
    pre = daily_residuals[
        (daily_residuals.index >= moment - pd.Timedelta(days=PRE_DAYS))
        & (daily_residuals.index < moment)
    ]
    post = daily_residuals[
        (daily_residuals.index >= moment)
        & (daily_residuals.index < moment + pd.Timedelta(days=POST_DAYS))
    ]
    return float(post.mean() - pre.mean())
```

From [`step_estimate`](src/atlas/ml/detectability.py). The last window has to end before the grid's first listed site, so the real campus stays out of the noise. The minimum detectable step is the 95th percentile of those estimates minus the 20th, a 5% false-positive line that a step of that size would clear in 80% of windows, and a grid with fewer than 12 dates gets no number.

### Event study

The same estimator is applied at the real start date and ranked against that grid's own pre-site windows. The two primary sites share one 5% error budget, so the early Los Lunas run has to clear a tighter line than a one-site test. The code raises before 15 December 2026, and the early path opens only for Los Lunas, once. Scoring and the locks are in [`src/atlas/ml/event_study.py`](src/atlas/ml/event_study.py), and the committed rules are [docs/analysis_plan.md](docs/analysis_plan.md).

## Design decisions

| Choice | Why | Cost |
|---|---|---|
| Untuned LightGBM defaults | Tuning on the pre-site windows would shrink the limit | A weaker short-range forecast than EIA's day-ahead on most grids |
| Fit a line, then trees on the remainder | Trees cannot extrapolate, and a flat trend would look like new load | A trend that is not a straight line stays in the residual |
| No lagged demand, and training stops a year before the test date | A lag, or training through the jump, would hide it | The baseline cannot use yesterday's demand |
| Limits use only windows that end before the first listed site | The real campus stays out of the noise estimate | Fewer windows, so each limit is rough |
| Inputs are stored under the freeze date | A later download cannot change a published result | A new question needs a new snapshot |
| The event study will not run before 15 December 2026 | A result computed early cannot be unseen | Meta Kuna waits. Los Lunas already had its one early run |
| The warehouse recomputes the verdicts in SQL, its query language | The build fails if those queries and Python disagree | Two copies of each rule |

## Evaluation

`make ci` runs ruff, ruff format, mypy in strict mode, sqlfluff, pytest with the network blocked, and a dbt build. dbt is the tool that builds the DuckDB warehouse. pytest is 128 passed. The dbt build on the real slice in [`tests/fixtures/lake`](tests/fixtures/lake) is 109 passed: 24 models, 81 data tests, and 4 seeds. That slice includes the rolling EIA tables, which is why it is higher than the 97 passed on the full-lake build recorded in [docs/log.md](docs/log.md).

- The step formula, the go rule, and the event-study locks are in [`tests/unit/test_detectability.py`](tests/unit/test_detectability.py), [`tests/unit/test_event_study.py`](tests/unit/test_event_study.py), and [`tests/unit/test_candidates.py`](tests/unit/test_candidates.py). An added step moves the estimate by exactly the step, on real PNM hours.
- Ingest, site locations, and recorded source responses are in [`tests/unit/test_eia.py`](tests/unit/test_eia.py), [`tests/unit/test_datacenters.py`](tests/unit/test_datacenters.py), [`tests/unit/test_geo.py`](tests/unit/test_geo.py), and [`tests/unit/test_source_check.py`](tests/unit/test_source_check.py). The cassettes are in [`tests/fixtures/cassettes`](tests/fixtures/cassettes).
- [`tests/unit/test_app.py`](tests/unit/test_app.py) loads the Streamlit page headless and recomputes the step from [`app/data/los_lunas_daily.csv`](app/data/los_lunas_daily.csv). It has to match the stored estimate within 0.01 MW.
- dbt restates the candidate rule, the limits, the go verdict, and the event-study p-value and interval. [`dbt/tests`](dbt/tests) fails the build if those disagree with the Python output. Adding 1 MW to the stored estimate fails that check.

## Limitations

- A jump in the residual is not a cause. Another new customer on the same date would look the same.
- Epoch's power and start dates are estimates from imagery and permits, not meters. The event study compares against 114 MW, the figure for the March 2026 window. The 31 October 2026 list puts the same campus at 147 MW.
- The limit assumes a step on one day. A slow ramp is easier to miss, and the limits on PJM (the Mid-Atlantic grid, 3,803 MW), ERCOT (most of Texas, 2,675 MW), and Southern Company (1,678 MW) sit above every listed site there.
- EIA-930 revises recent hours. Shifting the Los Lunas start 90 days later still needs data through 25 November 2026, and the rank p is as small as 45 comparison windows can make it.

## What I'd do next

- Score Meta Kuna on the 15 December 2026 snapshot and assign both labels together. `make m2` already refuses to start before that date, and the Los Lunas estimate stays fixed when that run happens.
- Add the 90-days-later shift, and report how far EIA's revisions move the 64 MW estimate. Both need that later snapshot.
- Meta-QTS Hillsboro 2 is out only because the boundary polygons overlap. On the October list it is 243 MW against Portland General's 44 MW limit. The event-study amendment uses 61 MW, the power at the August 2023 start, because the 243 MW figure comes later. Adding the site would be a dated amendment with a cited serving utility, not a change to this result.

## Run it

You need git, make, uv, and Python 3.12. Docker is only for the warehouse services and a full rebuild.

```bash
git clone https://github.com/VijayChamakuri/ai-power-atlas.git
cd ai-power-atlas
make setup
```

`make setup` creates `.env` from [`.env.example`](.env.example). Put a free [EIA data key](https://www.eia.gov/opendata/register.php) there. `make sources-check` also needs a [Census key](https://api.census.gov/data/key_signup.html) and a contact email for the SEC's EDGAR filing system.

```bash
make ci
make app
```

`make app` serves the one-page result at <http://localhost:8501>. It reads the four comma-separated files in [`app/data`](app/data) (about 100 KB) and does not need Docker or a key.

A rebuild from the frozen lake needs the archive `atlas-m1-frozen-lake.tar.gz` from the [data release](https://github.com/VijayChamakuri/ai-power-atlas/releases/tag/data-m1-2026-10-31) in the repo folder:

```bash
make up
make lake-restore
make analysis
```

`make up` starts Postgres, MinIO, Airflow, and MLflow, all bound to loopback. Airflow is at <http://localhost:8080>, MLflow at <http://localhost:5001>, and the MinIO console at <http://localhost:9001>. Local passwords are in `.env.example`.

`make pipeline` pulls the sources again instead of using the frozen files. A clean pull of that kind took 63 minutes. Open-Meteo's daily limit can stop the weather pull; the next run resumes at the counties already saved. `make m2` refuses to start before 15 December 2026. `make m2-early` has already run once and refuses a second time. `make paper` rebuilds the PDF and needs Google Chrome. Hashes and the rebuild notes are in [docs/log.md](docs/log.md).

## Repository map

| Path | What it holds |
|---|---|
| [`src/atlas/ml/detectability.py`](src/atlas/ml/detectability.py) | Detection limit, step estimate, and the go test |
| [`src/atlas/ml/event_study.py`](src/atlas/ml/event_study.py) | Event-study score and the date locks |
| [`src/atlas/ml/baseline.py`](src/atlas/ml/baseline.py) | Detrended LightGBM baseline |
| [`src/atlas/config.py`](src/atlas/config.py) | Freeze dates, windows, and model settings |
| [`src/atlas/ingest/`](src/atlas/ingest/) | Pulls for EIA-930, Epoch, weather, and site locations |
| [`dbt/`](dbt/) | DuckDB models and the SQL checks against Python |
| [`dags/`](dags/) | Airflow: full rebuild, hourly EIA pull, locked event study |
| [`app/`](app/) | Streamlit page and the four CSV files it reads |
| [`tests/`](tests/) | Pytest, recorded HTTP responses, and the lake slice |
| [`docs/paper.md`](docs/paper.md) | Working paper, also rendered as [`docs/paper.pdf`](docs/paper.pdf) |
| [`docs/analysis_plan.md`](docs/analysis_plan.md) | Method committed before the fits, plus dated amendments |
| [`docs/RESULTS.md`](docs/RESULTS.md) | Stored values, intervals, and the other grids |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | Windows, features, and model settings |
| [`docs/m1_detectability.md`](docs/m1_detectability.md) | Generated per-grid and per-site table |
| [`docs/m2_early_los_lunas.md`](docs/m2_early_los_lunas.md) | Generated early-run table |
| [`docs/log.md`](docs/log.md) | Build log, input hashes, and differences from the plan |
| [`Makefile`](Makefile) | `setup`, `ci`, `pipeline`, `app`, and the locked M2 commands |
