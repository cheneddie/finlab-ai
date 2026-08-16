# Fabio MTX Strategy Edge — Full Research Report

## Executive conclusion

The 2025 MTX file is sufficient to test Auction Market structure, Volume Profile location, price-path response, execution timing, and risk/cost sensitivity, but **not** Fabio's true Bid/Ask aggressor Delta, CVD, Footprint imbalance, queue dynamics, or iceberg/replenishment behavior.

The first complete pass does **not** support a robust, cost-surviving Fabio strategy from structure alone. The most informative finding is narrower and more useful:

> A failed auction is not itself an edge. The measurable improvement appears after the market re-enters Value **and then produces opposite-direction price follow-through**. Waiting one more tick / roughly one second materially improves the fade distribution. This is consistent with the hypothesis `Aggression -> Failure -> Opposite Response -> Execute`, but the remaining gross edge is too thin to survive a 0.5-point round-trip friction assumption reliably.

This means the next decisive test is not more parameter optimization on TOV/VOV. It is obtaining **true aggressor-classified trades (Bid/Ask)** and testing whether Fabio's Order Flow confirmation adds enough incremental information to make the response-confirmed setup survive costs.

---

## Phase 0 — Data QA

Source: `MTX_2025.parquet`.

- Rows: **39,416,621**.
- Raw volume sum: **108,060,010**.
- Timestamp backward transitions: **0**.
- Adjacent same-second rows: **31,047,171**.
- Integer-price ratio: **100%**.
- Even-volume ratio: **100%**.
- `side` counts: -1 = **11,025,973**, 0 = **17,396,367**, +1 = **10,994,281**.
- `side == sign(price_t-price_{t-1})`: **100%** across the full source.

### Hard processing rules

1. Preserve source physical row sequence; **never re-sort same-second transactions**.
2. Filter `product == MTX`.
3. Keep only valid outright month contracts for the selected research universe.
4. Remove all `/` calendar-spread / combination expiries.
5. Construct intraday profiles independently within the active contract/session; never contaminate a profile with spread prices or back-adjusted contract transitions.

### Important limitation discovered

`side` is not exchange aggressor-side. It is an uptick/downtick/unchanged classifier. Any `tick_delta_proxy` result below is therefore a **price-path proxy**, not evidence for true Fabio Delta/CVD.

---

## Phase 1 — Auction event engine

Reference structure:

- Rolling **30-minute completed** Volume Profile.
- Value Area = **70%**.
- POC / VAH / VAL are frozen for the next event observation.
- Breakout event begins when physical tick sequence first leaves the frozen VAH/VAL.
- Observation window = **60 seconds**.
- Outcome horizon = **600 seconds**.
- First-passage barrier = max(10 points, 20% of reference Value width).
- Event cooldown = **660 seconds** to reduce repeated counting of the same move.

Full-year event file contains **4,101** non-overlapping auction events; Phase 1–6 modelling uses **3,944 resolved** first-passage outcomes and 157 unresolved cases.

---

## Phase 2 — Acceptance / rejection predictive power

Train/test split: before **2025-09-01** vs 2025-09-01 onward.

Base continuation rate:

- Train: **49.9%**.
- OOS: **52.5%**.

Incremental logistic OOS results:

| Through layer | OOS AUC | Accuracy | Brier |
|---|---:|---:|---:|
| structure | 0.509 | 50.4% | 0.250 |
| location | 0.495 | 49.2% | 0.251 |
| acceptance | 0.523 | 51.4% | 0.250 |
| flow proxy | 0.528 | 52.7% | 0.250 |
| response | **0.532** | 52.6% | 0.249 |

Interpretation: simple TOV/VOV/structure variables are not enough to turn Balance/Imbalance classification into a strong directional predictor.

---

## Phase 3 — Location

Location variables were added after structure rather than assumed to be causal. In leave-one-layer-out tests, removing location did not degrade OOS AUC; the full model was 0.532 and the model without location was 0.536.

This does **not** prove VAH/VAL/LVN concepts are useless. It shows that the implemented broad location features, without true order-flow response, do not explain a stable directional edge in this dataset.

---

## Phase 4 — Available flow proxy

Because `side` is exactly the sign of the last-price change, the research only uses it as `tick_delta_proxy` / uptick-downtick volume.

Adding this proxy raises OOS AUC only modestly (0.523 -> 0.528). It must not be interpreted as validation of CVD, Footprint imbalance, or aggressor Delta.

---

## Phase 5 — Flow response / rejection confirmation

This became the most informative phase.

### Immediate failed-auction fade

The train-selected immediate re-entry fade (`exc=0.07|re=60|buf=3|tg=2R`) was:

- Train: **-0.130R/trade**.
- OOS: **-0.196R/trade**.
- OOS PF: **0.728**.

So `failed auction -> immediately fade` is not supported.

### Response confirmation

Instead of executing at the first re-entry tick, the engine tests confirmation delays while preserving source transaction order.

Train-selected response-confirmed rule:

`exc=0.07 | re-entry <= 30s | stop buffer=3 | target=2R | delay=next_1s`

Results:

- Train n = **1,510**, gross mean = **+0.170R**, PF = **1.283**.
- OOS n = **694**, gross mean = **+0.062R**, PF = **1.097**.
- OOS after 0.5-point equivalent round-trip cost = **-0.051R**.
- OOS after 1-point equivalent cost = **-0.163R**.

This is the strongest structural finding of the study: **opposite price response matters more than rejection alone**.

### Walk-forward response-confirmation

Window 2025-09-01 -> 2025-11-01:

- Gross: **+0.024R**, PF 1.036.
- 0.25-point cost: **-0.034R**.
- 0.5-point cost: **-0.093R**.

Window 2025-11-01 -> 2026-01-01, independently re-selected training rule:

- Gross: **+0.093R**, PF 1.205.
- 0.25-point cost: **+0.024R**.
- 0.5-point cost: **-0.046R**.

The gross response effect recurs, but friction sensitivity remains severe.

---

## Phase 6 — Interactions / expert compression

- Interpretable decision-tree OOS AUC: **0.511**.
- Nonlinear interaction model OOS AUC: **0.510**.

No broad nonlinear combination of the available structure/location/tick-direction-proxy variables reproduced a strong Fabio-like classifier.

This supports the hypothesis that the missing information may be in the unavailable layer: true aggressor flow + price response at selected locations, rather than a generic nonlinear combination of public profile variables.

---

## Phase 7 — Execution

### Accepted-breakout continuation retest

Train-selected rule: `hold=30|thr=0.90|band=0.10|tr=2`.

- Train gross: **+0.062R**.
- OOS gross: **+0.020R**.
- OOS PF: **1.030**.
- OOS with 0.5-point cost: **-0.058R**, PF 0.917.

This is too thin to call a tradable edge from this single year.

### Critical implementation incident and fix

An early execution pass produced implausibly large fade returns. Stress testing found an indexing bug: an event-relative index had been used as a day-array absolute index. The result was invalidated, fixed (`global_index = event_index + local_index`), and the full execution phase was rerun.

A regression test now reconstructs 60 real candidate trades from `entry_seq`; **60/60** stop/target/R outcomes match the execution engine exactly. Unit tests also cover contract filtering, expiry calendar, Value Area determinism, source ordering, and `side` semantics.

---

## Phase 8 — Risk management

Risk policies were evaluated only after fixing the execution setup.

Key principle confirmed: position sizing cannot rescue a negative expectation. The continuation setup's small gross edge disappears under modest point-equivalent friction, so daily stops / max-trade caps do not create an edge ex nihilo.

---

## Phase 9 — Ablation

Full structural classifier OOS AUC = **0.532**.

Leave-one-layer-out results show no single available layer creates a large edge; removing acceptance hurts most, but even the complete available model remains weak.

For the continuation execution family, train-defined quality ranking did not improve OOS trade expectancy; top-quartile OOS quality actually underperformed the full set.

---

## Phase 10 — Robustness

The validation code segments OOS results by:

- direction,
- calendar month,
- session bucket,
- Value-width regime,
- parameter neighborhood.

The important practical result is not a hidden profitable sub-bucket; it is that the gross edge is small enough that transaction friction dominates many subsets.

---

## Phase 11 — Walk-forward

Accepted-breakout continuation walk-forward gross results:

- Jul-Sep test: **+0.069R**, but **-0.022R** at 0.5-point cost.
- Sep-Nov test: **-0.027R** gross.
- Nov-Jan test: **-0.022R** gross.

This rejects the idea that a single optimized acceptance threshold is robust across 2025.

Response-confirmed failed-auction fade is more promising gross, but also fails 0.5-point cost consistently enough that it cannot yet be called tradable.

---

## Phase 12 — Verdict

### What is supported

1. Market response after a failed auction contains more information than the failed auction label itself.
2. Waiting for opposite-direction follow-through materially improves the failed-auction fade distribution.
3. This aligns conceptually with Fabio's emphasis on confirmation rather than blindly fading Value edges.

### What is not supported

1. Simple Balance/Imbalance classification as a strong standalone predictor.
2. TOV/VOV alone as a robust continuation signal.
3. Immediate failed-auction fade.
4. Accepted-breakout retest as a cost-robust MTX strategy in this 2025 sample.
5. Any claim that true Fabio Delta/CVD/Footprint edge has been tested — the source data cannot support that claim.

### Strongest remaining hypothesis

The next experiment should add **true Bid/Ask aggressor classification** (or TBBO/market-depth data) and test:

`high-quality location -> aggressive flow -> poor price impact / absorption -> opposite response -> execute`

against the same setup **without** the aggressor-flow condition.

The decisive statistic is the incremental, out-of-sample, after-cost EV added by true order flow. If that increment is small, then Fabio's public order-flow layer is unlikely to be the transferable alpha. If it is large and robust, that identifies the missing edge.

---

## Reproducibility / integrity checks

- No source-row re-sorting.
- Explicit physical `seq` carried through event and trade engines.
- 5 core unit tests passing.
- 60 real execution candidates independently reconstructed from raw Tick sequence: **0 mismatches**.
- Observation/features separated from future outcome horizon to reduce leakage.
- Raw Parquet is excluded from GitHub.
