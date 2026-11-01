# ADR-0002: M1 go or pivot

Status: accepted.

Date: 2026-11-01

## Question

Can the load of a large campus be detected in hourly balancing authority demand at all?

## Result

The rule in [docs/analysis_plan.md](../analysis_plan.md) says **go**, on two sites only. Numbers come
from [docs/m1_detectability.md](../m1_detectability.md).

| Site | BA | Epoch power MW | Minimum detectable MW | Implied utilization |
|---|---|---|---|---|
| Meta Kuna | IPCO | 198 | 98 | 0.49 |
| Meta Los Lunas | PNM | 147 | 77 | 0.52 |

Neither relies on utilization above 80%, so the rule does not call the evidence weak. Both also clear
the highest MDE in the sensitivity table, which is not pre-registered: 106 MW for IPCO and 85 MW for
PNM. Los Lunas was at 114 MW until 2026-10-26, which also clears its 85 MW.

The method cannot see the largest campuses at BA level:

| Site | BA | Epoch power MW | Minimum detectable MW | Result |
|---|---|---|---|---|
| Anthropic-Amazon New Carlisle | PJM | 1,244 | 3,803 | Below the MDE |
| Microsoft Fairwater Atlanta | SOCO | 859 | 1,678 | Below the MDE |
| Colossus 2 | TVA | 1,276 | 846 | Above, but on-site power flag |
| OpenAI Stargate Abilene | ERCO | 865 | 2,675 | Below the MDE, and flagged |

SWPP, AZPS, SRP, and WALC have too little history before their first sites and get no number.

New Carlisle clears the AEP zone's 590 MW MDE, at implied utilization 0.47. That is the secondary
analysis, which cannot make a go alone. The zone's `e(t)` values are all positive, from 23 to 909 MW,
so its demand was already beating a linear trend before the first listed site.

## Limits on this go

- It says these two sites could be seen. It does not say they were. No residual has been computed on
  or after a real energization date.
- MDEs are rough. Each `e(t)` spans 545 days, and the dates are 30 days apart. Some are unstable:
  SOCO's ranges from 503 to 2,388 MW in the sensitivity table.
- MDE assumes a sharp step, and real campuses ramp over months. Epoch's power is an estimate of
  facility power, not metered draw.
- Epoch's first date for Kuna is 2026-06-01, so a 180-day post-window is not complete until about
  2026-11-28, after this freeze.
- Both sites sit on Meta campuses in small BAs. A result there says little about PJM or ERCOT.
- Kuna's Epoch notes describe an offsetting solar array. Text search did not flag it, and off-site
  solar would not reduce BA demand, but its connection should be confirmed before M2.
- 10 sites are out only because they fall inside overlapping polygons. Meta-QTS Hillsboro 2 is the
  strongest, at implied utilization 0.18 against PGE, and has data since 2023.

## Decision

Vijay Shankar Chamakuri, 2026-11-01: go, with a narrower M2.

1. Primary event study on IPCO and PNM, with a fresh snapshot once Kuna has 180 days.
2. Before M2, cite the serving utility for overlap sites and amend the plan, starting with Hillsboro.
3. Keep the AEP zone for New Carlisle as a labeled secondary result.
4. State plainly that single campuses are below detection in PJM, ERCOT, and SOCO at BA level.

Aggregating many campuses per ISO stays open as the follow-up for large markets.
