# Fabio MTX V3/V4 Optimization & Holdout Report

## Executive conclusion

The earlier V1 conclusion (very little transferable edge) is **superseded**. It was based on an overly coarse implementation that omitted key Fabio playbook structure and under-searched the parameter space.

V3 rebuilt the strategy causally and layer-by-layer:

`previous-day profile -> full auction attempt -> clear reclaim / accepted displacement -> causal leg -> leg volume profile -> LVN -> first valid pullback -> execution -> stop/target`

All market-state/location/execution parameters were optimized on **2025-01 through 2025-08 Discovery only**. The primary candidates were frozen before applying them to **2025-09 through 2025-12 Holdout**.

## 1. Strongest transferable result: MR Broad

Frozen MR Broad rules:

- previous-day 80% Value Area
- 08:45-09:30 only
- failed auction excursion >= 2% of Value Width
- clear reclaim = 8% of Value Width within 60 seconds
- causal reclaim leg confirmed after 8 points
- reclaim-leg volume profile: smoothing 1, `valley_d55` LVN
- LVN must be in the middle of prior Value
- first valid LVN pullback, 1-point tolerance
- structural stop: 6 points beyond LVN
- target: 0.75R
- max hold: 300 seconds

### Frozen performance

| Split | Trades | Gross EV | Win rate | PF |
|---|---:|---:|---:|---:|
| Discovery | 30 | +0.529R | 83.3% | 4.17 |
| Holdout | 30 | +0.587R | 86.7% | 5.41 |

A more conservative execution reconstruction that uses the **actual first Tick beyond the stop** (rather than forcing all stops to exactly -1R) still gives Holdout:

- Gross EV: **+0.572R/trade**
- 0.5-point equivalent cost: **+0.489R/trade**
- 1.0-point equivalent cost: **+0.405R/trade**

## 2. Execution latency sensitivity

Conservative MR Broad, Holdout, with 0.5-point equivalent round-trip cost:

| Entry latency | EV |
|---|---:|
| Signal Tick | +0.489R |
| Next Tick | +0.174R |
| 2 Ticks | +0.264R |
| 5 Ticks | +0.007R |
| 1 second | +0.077R |

Interpretation: the edge is **execution-speed sensitive**, but it is not an artifact of requiring the exact same physical Tick. A next-Tick execution remains positive in Holdout. Around 5 Ticks to 1 second, much of the edge is consumed.

## 3. Cluster bootstrap: same-day setups are not treated as independent

MR Broad Holdout, 0.5-point cost, resampling **trading days as clusters** (20,000 bootstrap draws):

- point EV: **0.504R**
- 95% cluster-bootstrap interval: **[0.316, 0.678] R**
- bootstrap probability EV > 0: **100.00%**

This addresses the concern that one day can contain multiple correlated setups.

## 4. Parameter-neighborhood transfer

A pre-defined local neighborhood around MR Broad was assessed without selecting a new Holdout optimum:

- stop buffer: 4-8 points
- target: 0.50R-1.00R
- horizon: 180-600 seconds
- 125 neighboring configurations total

At 0.5-point cost:

- Discovery profitable configurations: **100.0%**
- Holdout profitable configurations: **100.0%**
- Holdout median EV across the entire neighborhood: **+0.368R**
- Holdout worst configuration in this neighborhood: **+0.097R**

This is strong evidence that the result is a **parameter plateau**, not a single exact stop/target point.

## 5. Passive-limit V4 variant

Discovery-only execution optimization also produced a passive-limit variant (`V4_STABLE`):

- entry = 4 points deeper than the LVN in the pullback direction
- stop = 3% of Value Width
- target = min(POC room, 0.5R)
- max hold = 45 seconds

Holdout, touch-fill assumption:

- 27 fills / 30 setups
- gross EV: +0.318R
- 0.5-point cost: **+0.202R**
- PF: 2.09

Queue/fill uncertainty is material. Requiring a full one-point trade-through before assuming fill weakens the result materially. However, direct Time & Sales evidence shows that about **77.8%** of Holdout fills traded through the limit within the first second, with a median of 4 prints at the limit. Therefore the true result is likely between the optimistic touch-fill and conservative full-penetration cases; MBO/queue data is needed to resolve it.

## 6. Regime evidence

Using prior-day range terciles fit on Discovery only and applied unchanged to Holdout:

- high-volatility prior-day regime: strongest Holdout behavior
- mid regime: weak/negative in the small Holdout sample
- both long and short directions remain positive gross in Holdout
- the edge is strongest before roughly 09:05; 09:05-09:14 is much weaker in Holdout

These are **diagnostics, not new filters**. No Holdout-based regime filter has been added to the frozen strategy.

## 7. Daily-risk sensitivity

The result does not depend on taking every repeated setup on a busy day. For V4 Stable at 0.5-point cost, limiting to the first trade of each day still leaves about +0.19R/trade in Holdout. For the original MR Broad, limiting daily trades also preserves positive performance.

## 8. What was wrong with V1

V1 omitted or simplified several core mechanisms:

1. It used rolling 30-minute Value rather than Fabio-style balance/reference context.
2. It treated tiny boundary crossings as separate failed auctions instead of one auction attempt with hysteresis.
3. It entered directly on re-entry instead of building a **causal reclaim leg**.
4. It did not profile that reclaim leg and select its LVN.
5. It under-searched stop, target, time, location, reclaim and response parameters.
6. It initially scored structural hit-rate more heavily than actual R expectancy.

V3 corrected these points and also fixed duplicate-setup inflation and previous relative-vs-absolute index errors. Regression checks are now part of the codebase.

## 9. Evidence boundary

The supplied `side` field equals `sign(price[t]-price[t-1])`; it is **not true Bid/Ask aggressor classification**. Therefore this study validates the transferable **Auction Market / Volume Profile / LVN / price-response** portion of the Fabio playbook, but it still cannot validate his true Footprint/CVD/aggression layer.

The next decisive test needs true Bid/Ask classified trades (or TBBO/MBO). That should be added as an incremental layer to the already-frozen structural model, not used to redesign the structural model after seeing Holdout.

## Current verdict

The statement “Fabio-style edge is almost absent” is no longer supported by the corrected research.

The strongest current evidence is that **failed-auction context + causal reclaim leg + reclaim-leg LVN pullback** carries a real and reasonably broad MTX intraday edge in 2025, especially when execution occurs very quickly. The direct MR Broad implementation survives a 4-month frozen Holdout, costs, day-cluster bootstrap and a broad local parameter neighborhood.

The remaining major uncertainty is **microstructure execution** (true queue/fill, Bid/Ask aggression and Footprint confirmation), not whether the structural layer contains any edge.
