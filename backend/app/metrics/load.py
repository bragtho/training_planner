"""Performance Management: CTL (Fitness), ATL (Muedigkeit), TSB (Form)."""

from __future__ import annotations

from datetime import date, timedelta
from math import exp

CTL_DAYS = 42
ATL_DAYS = 7


def compute_pmc(
    daily_tss: dict[date, float],
    start: date | None = None,
    end: date | None = None,
    ctl0: float = 0.0,
    atl0: float = 0.0,
) -> list[dict]:
    """Taegliche CTL/ATL/TSB-Reihe. TSB ist die Form am Morgen, d. h. CTL/ATL des Vortags (wie TrainingPeaks)."""
    if not daily_tss and (start is None or end is None):
        return []
    start = start or min(daily_tss)
    end = end or max(daily_tss)
    k_ctl = 1 - exp(-1 / CTL_DAYS)
    k_atl = 1 - exp(-1 / ATL_DAYS)
    ctl, atl = ctl0, atl0
    rows = []
    d = start
    while d <= end:
        load = daily_tss.get(d, 0.0)
        tsb = ctl - atl
        ctl += (load - ctl) * k_ctl
        atl += (load - atl) * k_atl
        rows.append({"date": d, "tss": load, "ctl": ctl, "atl": atl, "tsb": tsb})
        d += timedelta(days=1)
    return rows


def weekly_ramp_rate(rows: list[dict]) -> float | None:
    """CTL-Zuwachs der letzten 7 Tage."""
    if len(rows) < 8:
        return None
    return rows[-1]["ctl"] - rows[-8]["ctl"]
