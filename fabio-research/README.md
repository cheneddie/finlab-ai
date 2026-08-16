# Fabio MTX Auction Research

This repository contains an order-preserving research pipeline for testing the parts of Fabio Valentini's Auction Market / Volume Profile / Order Flow framework that can be evaluated from the supplied 2025 MTX tick-style Parquet file.

## Critical data rule

**Never re-sort the source rows.** The timestamp is only second-resolution, but same-second rows are already in transaction sequence. Every loader carries a physical `_seq`/`seq` index and all event/execution logic preserves source row order.

## Dataset facts discovered

- 39,416,621 rows, 38 row groups.
- Columns: `datetime`, `product`, `expiry`, `price`, `volume`, `side`.
- Timestamps are nondecreasing and have no sub-second component, but 31,047,171 adjacent records share the same second.
- Calendar-spread/combination expiries are present and are excluded from outright-contract research.
- `side` is **not aggressor-side Bid/Ask classification**. Across the full file it matches `sign(price_t-price_{t-1})` exactly; therefore it is only a tick-direction proxy and must not be called true Delta/CVD.
- `volume` is always even in this file; absolute volume interpretation should remain source-specific. Ratio/profile calculations are invariant to a constant scale factor.

## Research phases

0. Data QA and contract/session filtering.
1. Build rolling 30-minute Volume Profile; compute POC/VAH/VAL.
2. Detect non-overlapping VAH/VAL breakout events and classify future first-passage continuation vs failure.
3. Test location features (profile edge, POC/VWAP distance, previous-day levels).
4. Test available flow proxy (uptick/downtick volume), explicitly separated from true aggressor flow.
5. Test price-response / rejection confirmation.
6. Test nonlinear interactions and ablations.
7. Convert signals into executable fade/continuation rule families.
8. Stress position/risk rules and point-equivalent transaction costs.
9. Ablation / quality filtering.
10. Segment by direction, month, time bucket, and volatility/value-width regime.
11. Walk-forward validation.
12. Evidence-based verdict and data limitations.

## Main findings from 2025 MTX

- Broad acceptance/rejection classification is near-random OOS: full logistic AUC 0.532; nonlinear model AUC 0.510.
- Immediate failed-auction re-entry fade is negative OOS before costs.
- Accepted-breakout retest is only slightly positive gross OOS and fails a modest 0.5-point round-trip cost stress.
- A more Fabio-like sequence — **failed auction -> re-entry -> wait for opposite price response -> execute** — is materially better than immediate fade. Train-selected `next_1s` confirmation produced +0.062R OOS gross, but -0.051R after a 0.5-point equivalent round-trip cost.
- Walk-forward response-confirmation tests show the same pattern: thin gross structure exists, but does not survive 0.5-point cost consistently.
- Therefore this file does **not validate a complete Fabio edge**. The strongest missing layer is true aggressor-side Bid/Ask flow / footprint response; this Parquet cannot test it.

See `reports/FABIO_MTX_FINAL_REPORT.md` for the full phase-by-phase report.

## Run

The included native reader avoids a PyArrow dependency for this specific flat Snappy/dictionary Parquet format.

```bash
PYTHONPATH=src python scripts/run_events.py /path/to/MTX_2025.parquet reports
PYTHONPATH=src python scripts/run_analysis.py
PYTHONPATH=src python scripts/run_execution.py
PYTHONPATH=src python scripts/run_validation.py
PYTHONPATH=src python scripts/run_response_confirmation.py
PYTHONPATH=src python -m pytest -q tests
PYTHONPATH=src python scripts/run_regression_checks.py
```

The raw market-data file is intentionally **not committed**.

## Reproducibility cautions

- Keep the original Parquet row order.
- Do not infer true CVD from `side` in this file.
- Do not mix calendar spreads/combination contracts with outright MTX.
- Do not back-adjust prices when constructing intraday Volume Profiles.
- Keep feature observation windows strictly before outcome windows to avoid leakage.
- All cost figures in this research are point-equivalent round-trip friction assumptions, not a broker-specific fee model.
