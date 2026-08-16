from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ProfileLevels:
    poc: float
    val: float
    vah: float
    vwap: float
    width: float
    total_volume: float
    edge_low_ratio: float
    edge_high_ratio: float
    concentration: float


def value_area(profile: dict[int, float], pct: float = 0.70) -> ProfileLevels | None:
    """Calculate contiguous value area by expanding outward from POC.

    Tie-breaking for POC uses proximity to profile VWAP, then lower price, to
    keep the procedure deterministic. Expansion chooses the adjacent price
    level with more volume (ties expand downward first). Missing integer price
    levels are represented as zero-volume levels.
    """
    if not profile:
        return None
    items = [(int(p), float(v)) for p, v in profile.items() if v > 0]
    if not items:
        return None
    minp = min(p for p, _ in items); maxp = max(p for p, _ in items)
    prices = np.arange(minp, maxp + 1, dtype=np.int64)
    vols = np.zeros(len(prices), dtype=float)
    for p, v in items:
        vols[p - minp] += v
    total = float(vols.sum())
    if total <= 0:
        return None
    vwap = float(np.dot(prices.astype(float), vols) / total)
    maxv = float(vols.max())
    cands = np.flatnonzero(vols == maxv)
    poc_idx = int(cands[np.argmin(np.abs(prices[cands] - vwap))])
    lo = hi = poc_idx
    cum = float(vols[poc_idx])
    target = pct * total
    while cum < target and (lo > 0 or hi < len(vols) - 1):
        vdn = vols[lo - 1] if lo > 0 else -1.0
        vup = vols[hi + 1] if hi < len(vols) - 1 else -1.0
        if vup > vdn:
            hi += 1; cum += float(vols[hi])
        else:
            lo -= 1; cum += float(vols[lo])
    poc = float(prices[poc_idx]); val = float(prices[lo]); vah = float(prices[hi])
    width = max(1.0, vah - val)
    median_pos = float(np.median(vols[vols > 0])) if np.any(vols > 0) else 1.0
    edge_low_ratio = float(vols[lo] / median_pos) if median_pos else 0.0
    edge_high_ratio = float(vols[hi] / median_pos) if median_pos else 0.0
    probs = vols[vols > 0] / total
    concentration = float(np.sum(probs * probs) * len(probs))
    return ProfileLevels(poc, val, vah, vwap, width, total,
                         edge_low_ratio, edge_high_ratio, concentration)


def add_profile(dst: dict[int, float], src: dict[int, float], sign: float = 1.0) -> None:
    for p, v in src.items():
        nv = dst.get(p, 0.0) + sign * v
        if nv <= 1e-12:
            dst.pop(p, None)
        else:
            dst[p] = nv
