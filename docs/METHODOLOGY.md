# Method settings

These are the values in [`src/atlas/config.py`](../src/atlas/config.py), [`src/atlas/ml/features.py`](../src/atlas/ml/features.py), and [`src/atlas/ml/candidates.py`](../src/atlas/ml/candidates.py). The committed plan is [analysis_plan.md](analysis_plan.md). A change to one of these numbers is a dated amendment there before it is a change in code. The reason for each value is the comment in the code, shortened below.

## Freezes

| Name | Value | Why it is that day |
|---|---|---|
| History start | 2019-01-01 | Start of the EIA-930 history the plan uses |
| Detectability freeze | 2026-10-31 | Day the first-stage snapshots were taken |
| Early event-study freeze | 2026-11-01 | Approval day for the one Los Lunas run |
| Full event-study freeze | 2026-12-15 | After Kuna's 180 days end on 2026-11-28, so revisions can settle |

The early path names one site, Meta Los Lunas. Everything else still waits for 2026-12-15.

## Who is tested

A balancing authority is a candidate when listed campus power is at least 2% of its peak hour (`CANDIDATE_SHARE`). The peak is the max of the cleaned series over the 365 days ending at the last hour that authority actually reported, so a series that stopped early is not judged on a partial year.

Hours at or below zero, or above 3 times the median of the positive hours, are dropped before the peak and before the model fit. The raw hours stay in the lake.

## Windows

| Setting | Value | Role |
|---|---|---|
| `PSEUDO_STEP_DAYS` | 30 | How far apart the test dates are |
| `TRAIN_GAP_DAYS` | 365 | Training stops a year before the test date. That year is also the pre-window |
| `MIN_HISTORY_DAYS` | 730 | Two years, so the trend is not fit on one season |
| `POST_DAYS` | 180 | Days after the test date in the step estimate |
| `MIN_PSEUDO_DATES` | 12 | Below this, the grid gets no detection limit |
| `NULL_QUANTILE` | 0.95 | One-sided 5% false-positive line |
| `POWER_QUANTILE` | 0.20 | A step of the limit clears the line in 80% of windows |
| `WEAK_UTILIZATION` | 0.80 | If every passing site needs more than this share of its listed power to be seen, the plan's rule says `go_weak_evidence` |

The minimum detectable step is the 95th percentile of the pre-site estimates minus the 20th. Adding S MW after the test date adds S to the estimate, which is why the gap between those percentiles is the step found in 80% of windows.

## Baseline

LightGBM is left on common starting values. Tuning them against the pre-site windows would shrink the limit.

| Parameter | Value |
|---|---|
| `n_estimators` | 300 |
| `learning_rate` | 0.05 |
| `num_leaves` | 31 |
| `random_state` | 1 |
| `deterministic` | true |
| `force_row_wise` | true |
| `n_jobs` | 4 |
| `verbose` | -1 |

Features, with no lagged demand: `hour`, `day_of_week`, `month`, `holiday`, `temperature_f`, `humidity`, `cooling_degree`, `heating_degree`. Degree hours use a 65 F base, the base in US degree-day reporting. Weather is a population-weighted average of up to 10 county centroids. Each grid uses the time zone of most of its load. The zone table is `BA_TIMEZONES` in the config module.

A line is fit on the training demand first. LightGBM predicts the detrended series, and the line is added back.

## Event study

| Setting | Value | Role |
|---|---|---|
| `M2_ALPHA` | 0.05 | Holm's step-down adjustment across the two primary sites, one-sided, so the pair keeps a 5% false-positive rate |
| `M2_EARLY_PASS_P` | 0.025 | Half of 0.05. Below this, the early site passes at every p-value the other site could return |
| `M2_SUPPORT_P` | 0.10 | Other-grid placebo. The pool is small, so the line is coarse |
| `M2_LEAD_DAYS` | 180 | A window this far before the start should show no campus load |
| `M2_SHIFT_DAYS` | 90 | How far the estimated start date is moved in the sensitivity check |
| `M2_DONOR_MIN_MEDIAN_MW` | 500 | Grids smaller than this are too noisy to use as donors |
| `M2_DONOR_MIN_COVERAGE` | 0.95 | A donor has to report at least 95% of hours |
| `EXTRACT_TOLERANCE_MW` | 0.01 | The app extract has to match the stored estimate within this |

Primary sites, fixed by Amendment 4. Start dates stay as frozen even if Epoch changes them later.

| Site | Grid | Start | Expected MW |
|---|---|---|---:|
| Meta Kuna | Idaho Power (IPCO) | 2026-06-01 | 198 |
| Meta Los Lunas | PNM (New Mexico) | 2026-03-01 | 114 |

The 114 MW for Los Lunas is the window figure. The detectability list on 2026-10-31 has the same campus at 147 MW. Secondary sites, which cannot change a label: Meta-QTS Hillsboro 2 on Portland General, expected 61 MW at the 2023-08-02 start (the 243 MW in the detectability table comes later, in 2024), and New Carlisle on the AEP zone at 1,244 MW (start 2025-06-23).

A result is `supported` only if the adjusted p-value is below 0.05, the estimate is positive, the lead window is at or below its threshold, the other-grid p-value is at or below 0.10, and the synthetic-control gap is positive. If the adjusted p-value is below 0.05 and one of those checks fails, the label is `suggestive`. Otherwise it is `null`.
