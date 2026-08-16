# Fabio MTX V3/V4 Robustness Appendix

## 1. Direct MR Broad execution stress

Frozen MR Broad, Holdout, conservative stop-fill reconstruction:

| Execution | Cost | EV/trade |
|---|---:|---:|
| Signal Tick | 0.0 pt | +0.572R |
| Signal Tick | 0.5 pt | +0.489R |
| Signal Tick | 1.0 pt | +0.405R |
| Next Tick | 0.5 pt | +0.174R |
| 2 Ticks later | 0.5 pt | +0.264R |
| 5 Ticks later | 0.5 pt | +0.007R |
| 1 second later | 0.5 pt | +0.077R |

The structural edge survives small execution delay, but much of it is consumed by ~5 physical Ticks to 1 second of delay.

## 2. Trading-day cluster bootstrap

Same-day trades are resampled as one cluster rather than treated as independent observations.

Holdout MR Broad:

- 30 trades on 16 trading days
- 0.5-point equivalent cost point estimate: +0.504R/trade
- 95% cluster-bootstrap interval: [+0.316R, +0.678R]
- P(EV > 0): approximately 100% in 20,000 resamples

At 1.0-point equivalent cost:

- point estimate: +0.420R
- 95% interval: [+0.230R, +0.594R]
- P(EV > 0): about 99.98%

## 3. Stop / target / horizon parameter plateau

A local neighborhood defined without selecting a new Holdout optimum was applied to both splits:

- stop buffer: 4-8 points
- target: 0.50R, 0.625R, 0.75R, 0.875R, 1.0R
- max hold: 180, 240, 300, 420, 600 seconds
- 125 configurations total

At 0.5-point equivalent cost:

- Discovery: 125/125 configurations positive
- Holdout: 125/125 configurations positive
- Holdout median EV: +0.368R
- Holdout worst EV: +0.097R

The frozen center is therefore part of a broad positive plateau rather than an isolated optimum.

## 4. LVN counterfactual and random-location placebo

The Market State and reclaim leg are held fixed while the trade location is changed.

Fixed shifts show that the true reclaim-leg LVN combines the highest coverage with strong expectancy. Moving the entry level toward POC by about 5 points leaves only 14/30 fills and approximately +0.008R/trade; deeper shifts generally reduce coverage and/or expectancy.

A stricter randomized placebo was also run:

- true LVN per-signal EV: **+0.611R**
- random neighboring-location mean EV: **+0.172R**
- 95th percentile of random-location EV: **+0.340R**
- 99th percentile: **+0.402R**
- random trials >= true LVN: **0 / 50,000**

No-fill random levels are counted as 0R, so the placebo cannot appear artificially strong by keeping only the rare random levels that happen to fill.

This is direct evidence that the reclaim-leg LVN adds information beyond failed-auction context alone.

## 5. Fixed-fraction equity Monte Carlo

Trading days are sampled as clusters, with 0.5-point equivalent cost and all same-day signals kept together.

### Holdout

| Risk per trade | Median return | 95th-percentile max drawdown |
|---|---:|---:|
| 0.25% | +3.83% | 0.55% |
| 0.50% | +7.82% | 1.10% |
| 1.00% | +16.18% | 2.19% |
| 2.00% | +34.60% | 4.35% |

These are resampling diagnostics from the observed 16 Holdout trading days, not forecasts of future return.

## 6. MR + Trend frozen portfolio

At 0.5-point equivalent cost:

### Holdout

- MR Broad alone: +0.504R/trade, 30 trades
- Trend Broad: +0.553R/trade, 3 trades
- Trend Robust: +1.563R/trade, 2 trades
- MR Broad + Trend Broad: +0.508R/trade, 33 trades
- MR Broad + Trend Robust: +0.570R/trade, 32 trades

Trend and MR overlap on very few trading days, suggesting potential diversification. However, Trend has only 2-3 Holdout trades and remains low-confidence evidence.

## 7. Why MR Broad transfers while high-R variants do not

The key distinction is extraction demand, not just entry quality.

- MR Broad: median MFE stays about 26 points in both Discovery and Holdout; typical target is only ~5 points.
- MR Robust: median MFE falls from ~85 to ~39 points; typical target is ~128 points.
- MR High-Payoff: median MFE falls from ~90 to ~36 points; typical target is ~126 points.

The high-R variants require a much stronger continuation regime. MR Broad monetizes the first, more persistent rotation after the LVN pullback.

## 8. Remaining evidence boundary

The current data has ordered Tick records but no true Bid/Ask aggressor classification. The `side` field is price-direction classification. Therefore:

- Auction Market structure: tested
- prior-profile state: tested
- failed auction / accepted displacement: tested
- causal leg profile: tested
- LVN pullback: tested
- price response: tested
- execution / stop / target / latency / costs: tested
- true Footprint Delta / CVD / Bid-Ask aggression / absorption: **not yet tested**
- queue-priority accuracy for passive limit fills: **not fully resolvable without MBO/depth**

The next dataset should add true aggressor-side or TBBO/MBO to the already-frozen structural models rather than reopening structural parameter selection after seeing the new data.
