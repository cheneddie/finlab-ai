# Why MR Broad Transfers Better Than High-R Variants

## Core finding

The stable edge is not primarily about reaching the full POC. It is about exploiting the first high-probability rotation after a failed auction and reclaim-leg LVN pullback.

### MR Broad

- Discovery median MFE: 26 points
- Holdout median MFE: 26 points
- Typical target: about 5 points (0.75R with ~6-point risk)
- Discovery gross EV: +0.529R/trade
- Holdout gross EV: +0.587R/trade

The target sits far inside the distribution of favorable excursion. Even the Holdout 25th-percentile MFE is about 10 points, still comfortably larger than the typical 5-point target.

### MR Robust

- Discovery median MFE: 85 points
- Holdout median MFE: 39 points
- Typical target: about 128 points
- Discovery: +3.925R/trade
- Holdout: -0.364R/trade

The structural entry still creates favorable movement, but the large target depends on a much stronger continuation regime than was present in Holdout.

### MR High-Payoff

- Discovery median MFE: 90 points
- Holdout median MFE: 36 points
- Typical target: about 126 points
- Discovery: +4.985R/trade
- Holdout: -1.0R/trade

All 17 Holdout trades failed the very large payoff target. The entry structure did not necessarily disappear; the extraction assumption was too aggressive for the new regime.

## Interpretation

The strongest transferable mechanism appears to be:

`failed auction -> clear reclaim -> causal reclaim leg -> reclaim-leg LVN pullback -> first rotation`

The fragile component is not the Location edge itself, but how much R is demanded from that edge.

This explains why optimizing only for maximum Discovery R can be misleading: a high-R target may monetize a temporary regime property, while the lower target captures the more persistent conditional price response.

## Segment stability of MR Broad

At 0.5-point equivalent cost, Holdout remains positive in both directions:

- short/fade-down direction: about +0.546R/trade
- long/fade-up direction: about +0.440R/trade

Using prior-day range terciles fit on Discovery only:

- low-vol Holdout sample is weak, but has only 2 trades
- mid regime: about +0.737R/trade, 6 trades
- high regime: about +0.500R/trade, 22 trades

By entry time:

- 08:45-08:54: about +0.746R/trade
- 08:55-09:04: about +0.202R/trade
- 09:05-09:14: about +0.479R/trade

These are diagnostics only. No Holdout-derived filter is added to the frozen strategy.

## LVN counterfactual

A frozen counterfactual test shifted the reclaim-leg LVN while preserving the same Market State and execution logic.

At 0.5-point cost in Holdout:

- true LVN: 30/30 fills, about +0.61R/trade
- 3-10 points deeper: lower fill rates and generally lower EV
- 5 points toward POC: 14/30 fills and about +0.008R/trade

Farther shifts sometimes show high EV only because 1-3 trades remain; those are not statistically meaningful.

This supports the conclusion that the reclaim-leg low-volume location adds information beyond the failed-auction context alone.
