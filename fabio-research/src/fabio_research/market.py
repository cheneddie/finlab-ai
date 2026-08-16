from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import numpy as np

from .parquet_native import NativeParquetFile

DAY_US = 86_400_000_000
SECOND_US = 1_000_000
DAY_START_SEC = 8 * 3600 + 45 * 60
DAY_END_SEC = 13 * 3600 + 45 * 60
EXPIRY_DAY_END_SEC = 13 * 3600 + 30 * 60
NIGHT_START_SEC = 15 * 3600
NIGHT_END_SEC = 5 * 3600

EPOCH_DATE = date(1970, 1, 1)


def date_from_day_id(day_id: int) -> date:
    return EPOCH_DATE + timedelta(days=int(day_id))


def day_id_from_date(d: date) -> int:
    return (d - EPOCH_DATE).days


def third_wednesday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (calendar.WEDNESDAY - first.weekday()) % 7
    return first + timedelta(days=offset + 14)


def next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def front_month_expiry(d: date) -> str:
    """Return front monthly MTX contract for the regular day session.

    Monthly MTX expires on the third Wednesday. The expiring contract remains
    the front contract through its final regular session; the next calendar
    month becomes front on the following day.
    """
    y, m = d.year, d.month
    if d > third_wednesday(y, m):
        y, m = next_month(y, m)
    return f"{y:04d}{m:02d}"


def front_month_expiry_at(d: date, sec_of_day: int) -> str:
    """Front monthly contract at a regular-session wall-clock second.

    On the monthly expiration date the expiring series stops at 13:30, while
    other regular-session contracts continue to 13:45. Therefore the next
    monthly series is treated as front after 13:30 on that date.
    """
    y, m = d.year, d.month
    exp_day = third_wednesday(y, m)
    if d > exp_day or (d == exp_day and sec_of_day >= EXPIRY_DAY_END_SEC):
        y, m = next_month(y, m)
    return f"{y:04d}{m:02d}"


def is_monthly_expiry(x: str) -> bool:
    return len(x) == 6 and x.isdigit()


@dataclass
class TickDay:
    trading_date: date
    seq: np.ndarray
    datetime_us: np.ndarray
    price: np.ndarray
    volume_raw: np.ndarray
    side_proxy: np.ndarray
    expiry: np.ndarray

    @property
    def volume(self) -> np.ndarray:
        # Keep the source volume scale unchanged. Every observed raw value is
        # even, but its vendor-specific absolute-volume convention has not been
        # independently verified. Profile shape, VAH/VAL/POC and volume ratios
        # are invariant to a constant scale factor.
        return self.volume_raw


class MTXDataset:
    def __init__(self, path: str | Path):
        self.parquet = NativeParquetFile(path)
        self.path = Path(path)
        self._row_group_bases = []
        base = 0
        for rg in self.parquet.row_groups:
            self._row_group_bases.append(base)
            base += int(rg["num_rows"])

    def iter_front_month_day_sessions(self, row_group_start: int = 0, row_group_end: int | None = None) -> Iterator[TickDay]:
        """Yield regular-session front-month ticks, preserving source row order.

        No sorting occurs. `seq` is the original physical row index in the
        Parquet file and is retained as an explicit invariant.
        """
        current_day: int | None = None
        buffers: dict[str, list[np.ndarray]] = {
            "seq": [], "datetime_us": [], "price": [], "volume_raw": [],
            "side_proxy": [], "expiry": []
        }

        def flush(day_id: int) -> TickDay | None:
            if not buffers["datetime_us"]:
                return None
            arrays = {k: np.concatenate(v) if len(v) > 1 else v[0] for k, v in buffers.items()}
            for v in buffers.values():
                v.clear()
            return TickDay(
                trading_date=date_from_day_id(day_id),
                seq=arrays["seq"], datetime_us=arrays["datetime_us"],
                price=arrays["price"], volume_raw=arrays["volume_raw"],
                side_proxy=arrays["side_proxy"], expiry=arrays["expiry"],
            )

        cols = ["datetime", "expiry", "price", "volume", "side"]
        rg_end = len(self._row_group_bases) if row_group_end is None else min(row_group_end, len(self._row_group_bases))
        for rg_idx in range(max(0, row_group_start), rg_end):
            base = self._row_group_bases[rg_idx]
            rg = self.parquet.read_row_group(rg_idx, cols)
            dt = rg["datetime"]
            day_ids = dt // DAY_US
            sec = (dt % DAY_US) // SECOND_US
            time_mask = (sec >= DAY_START_SEC) & (sec < DAY_END_SEC)
            if not np.any(time_mask):
                continue

            exp = rg["expiry"]
            active = np.empty(len(dt), dtype=object)
            for d_id in np.unique(day_ids[time_mask]):
                d = date_from_day_id(int(d_id))
                dm = day_ids == d_id
                base_contract = front_month_expiry(d)
                active[dm] = base_contract
                if d == third_wednesday(d.year, d.month):
                    late = dm & (sec >= EXPIRY_DAY_END_SEC)
                    if np.any(late):
                        y2, m2 = next_month(d.year, d.month)
                        active[late] = f"{y2:04d}{m2:02d}"
            mask = time_mask & (exp == active)
            idx = np.flatnonzero(mask)
            if idx.size == 0:
                continue

            fday = day_ids[idx]
            boundaries = np.r_[0, np.flatnonzero(np.diff(fday) != 0) + 1, len(idx)]
            for a, b in zip(boundaries[:-1], boundaries[1:]):
                ids = idx[a:b]
                d_id = int(fday[a])
                if current_day is None:
                    current_day = d_id
                if d_id != current_day:
                    item = flush(current_day)
                    if item is not None:
                        yield item
                    current_day = d_id
                buffers["seq"].append(base + ids)
                buffers["datetime_us"].append(dt[ids])
                buffers["price"].append(rg["price"][ids])
                buffers["volume_raw"].append(rg["volume"][ids])
                buffers["side_proxy"].append(rg["side"][ids])
                buffers["expiry"].append(exp[ids])

        if current_day is not None:
            item = flush(current_day)
            if item is not None:
                yield item
