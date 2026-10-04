"""Fitness-Kennzahlen eines Nutzers aus der Datenbank (gemeinsam genutzt von API und Coach)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity
from .load import compute_pmc, weekly_ramp_rate


def daily_tss(db: Session, user_id: int) -> dict[dt.date, float]:
    daily: dict[dt.date, float] = {}
    for a in db.scalars(select(Activity).where(Activity.user_id == user_id, Activity.tss.is_not(None))):
        d = a.start_time.date()
        daily[d] = daily.get(d, 0.0) + (a.tss or 0.0)
    return daily


def pmc_rows(db: Session, user_id: int, today: dt.date | None = None) -> list[dict]:
    """Taegliche CTL/ATL/TSB-Reihe bis heute; leer, wenn es keine Aktivitaeten mit TSS gibt."""
    daily = daily_tss(db, user_id)
    if not daily:
        return []
    return compute_pmc(daily, end=max(today or dt.date.today(), max(daily)))


def current_status(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    last = rows[-1]
    ramp = weekly_ramp_rate(rows)
    return {
        "ctl": round(last["ctl"], 1),
        "atl": round(last["atl"], 1),
        "tsb": round(last["ctl"] - last["atl"], 1),
        "ramp_rate": round(ramp, 1) if ramp is not None else None,
    }


def weekly_summary(db: Session, user_id: int, weeks: int = 8, today: dt.date | None = None) -> list[dict]:
    """TSS, Stunden und Anzahl Fahrten je Kalenderwoche (Montag-Sonntag), aelteste zuerst."""
    today = today or dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    first = this_monday - dt.timedelta(weeks=weeks - 1)
    acts = db.scalars(
        select(Activity).where(
            Activity.user_id == user_id, Activity.start_time >= dt.datetime.combine(first, dt.time.min)
        )
    )
    out = {first + dt.timedelta(weeks=i): {"week_start": (first + dt.timedelta(weeks=i)).isoformat(),
                                           "tss": 0.0, "hours": 0.0, "rides": 0} for i in range(weeks)}
    for a in acts:
        d = a.start_time.date()
        w = out.get(d - dt.timedelta(days=d.weekday()))
        if w is not None:
            w["tss"] += a.tss or 0.0
            w["hours"] += (a.duration_s or 0) / 3600
            w["rides"] += 1
    return [{**w, "tss": round(w["tss"]), "hours": round(w["hours"], 1)} for w in out.values()]
