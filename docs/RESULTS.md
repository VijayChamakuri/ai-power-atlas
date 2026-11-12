# Results

The README and Figure 9 report megawatts rounded to the nearest whole number, and the rank p-value rounded to three decimals. This note holds the stored values and the checks that are not in that table.

## Early event study: Meta Los Lunas

The files are `app/data/los_lunas_result.csv` and `app/data/los_lunas_daily.csv`, written by `atlas analyze early-extract` from the snapshot frozen on 2026-11-01. The generated one-row table is [m2_early_los_lunas.md](m2_early_los_lunas.md).

The stored step estimate is 63.76 MW. That is the mean residual over the 180 days from 2026-03-01, minus the mean over the 365 days before it. Those means are -30.07 MW (365 days) and +33.69 MW (180 days). Rounded to the nearest MW they are -30 and +34, and the rounded estimate is +64 MW. That is what Figure 9 prints. The difference of the rounded means is also 64, so the chart's three labels agree at whole MW.

The stored rank p-value is 1/46 = 0.02174, reported as 0.022. With 45 comparison windows, 1/46 is as small as this test can get. The early-run pass line is 0.025, which is half of the 0.05 budget, because Meta Kuna has not been scored (`M2_EARLY_PASS_P` in `src/atlas/config.py`). The observed 0.022 is the result. The 0.025 line is the rule for calling this one site a pass before Kuna runs.

| Check | Reported | Rule |
|---|---|---|
| Step estimate | +64 MW | Positive |
| 90% interval | +13 to +102 MW | Reported |
| Rank p | 0.022 | Below 0.025 for the early run |
| Epoch power for this window | 114 MW | Comparison, not a pass line |
| Lead window, 180 days before the start | -45 MW | At or below +51 MW |
| Start moved 90 days earlier | -5 MW | Reported only |
| Start moved 90 days later | not yet | Needs data through 2026-11-25 |
| Other-grid placebo, 20 grids | p = 0.095 | 0.10 or less |
| Synthetic control gap | +70 MW | Positive |

Stored values behind the rounded MW figures, from `los_lunas_result.csv`: estimate 63.76, interval 13.00 to 102.35, lead window -45.45, lead threshold 50.76, start minus 90 days -4.96, synthetic gap 69.81, other-grid p 0.09524. The label column is empty. [m2_early_los_lunas.md](m2_early_los_lunas.md) reads the early result as "passes the main test" and leaves the final label for the run with Meta Kuna.

Two power figures for the same campus measure different lists:

- 114 MW is the expected effect in the event study. It is the Epoch figure frozen for the window that starts 2026-03-01 (Amendment 4 in [analysis_plan.md](analysis_plan.md)).
- 147 MW is Epoch's figure on the 2026-10-31 detectability freeze. The go test uses 147 MW against PNM's 77 MW limit.

The 90% interval stops at 102 MW, so it does not reach the 114 MW window figure.

## Detectability

The generated table is [m1_detectability.md](m1_detectability.md). Figure 1 is [figures/fig1_site_map.png](figures/fig1_site_map.png).

Figure 1 counts 60 sites with power by the 31 October 2026 freeze, out of 77 US sites in the snapshot: 2 pass, 27 below the limit, 14 excluded, and 17 with no limit. Their listed power sums to 15,834.8 MW. The figure rounds each group to the nearest MW, 345, 6,673, 4,885, and 3,932, and those rounded groups add to the 15,835 MW printed on the chart. The 345 MW is Meta Kuna (198) plus Meta Los Lunas (147 on this freeze). The 6,673 MW bar is 6,672.8 MW before rounding, which is why the rounded groups add to 15,835 rather than 15,834.8.

| Site | Grid | Power in the go test | Detection limit | Result |
|---|---|---:|---:|---|
| Meta Kuna | Idaho Power | 198 MW | 98 MW | Passes |
| Meta Los Lunas | PNM | 147 MW | 77 MW | Passes |
| New Carlisle | PJM | 1,244 MW | 3,803 MW | Below the limit |
| Stargate Abilene | ERCOT | 865 MW | 2,675 MW | Below the limit, and flagged for on-site power |
| Fairwater Atlanta | Southern Company | 859 MW | 1,678 MW | Below the limit |

Limits in that table, and on Figure 6, are rounded to the nearest MW. The app extract keeps one decimal: 97.7 MW for Idaho Power and 76.5 MW for PNM. The ratio column is site power divided by that unrounded limit. Kuna's 2.03 is 198 / 97.7, printed beside a rounded limit of 98. Los Lunas's 1.92 is 147 / 76.5, printed beside 77. The same pairing is why Hillsboro's ratio is 5.50 beside a rounded limit of 44 (243 / 44.2).

Every grid, every site, the sensitivity ranges, and the baseline errors are in [m1_detectability.md](m1_detectability.md). On mean absolute percentage error the baseline beats a same-hour-last-week guess in every series. It also beats EIA's day-ahead forecast for PNM, Idaho Power, and Nevada Power, ties PacifiCorp West, and loses on the other series that have an EIA forecast. The baseline is given actual weather. EIA's number is a day-ahead forecast.

The sensitivity check is not part of the go test. Recomputing the limit on parts of the same pre-site windows gives 69 to 106 MW for Idaho Power and 67 to 85 MW for PNM, against campuses of 198 and 147 MW. The 114 MW window figure for Los Lunas also clears 85 MW. The column-by-column table is in the detectability note.
