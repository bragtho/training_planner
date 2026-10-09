import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from ..db import get_db
from ..integrations import strava
from ..metrics.bests import LEVEL_LABELS, classify
from ..metrics.power import mean_max_curve
from ..metrics.sports import is_cycling
from ..models import Activity, User
from ..security import current_user

router = APIRouter(tags=["bests"])

DEFAULT_DURATIONS = (5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 5400)
MAX_DURATIONS = 12

# Leistungskurve je Aktivitaet: {(activity_id, duration_s): {"watts", "start_s"} | None}. Spart bei jedem Aufruf das
# Neuberechnen aus den Rohdaten. ponytail: nur im Prozess-Speicher (Neustart leert ihn), bei Bedarf in die DB legen.
_cache: dict[tuple[int, int], dict | None] = {}


def _best_of(a: Activity, durations: tuple[int, ...]) -> dict[int, dict]:
    missing = [d for d in durations if (a.id, d) not in _cache]
    if missing:
        s = a.streams or {}
        watts = strava.resample_1hz(s.get("time") or [], s.get("watts") or [])
        found = {p["duration_s"]: p for p in mean_max_curve(watts, missing)}
        for d in missing:
            _cache[(a.id, d)] = found.get(d)
    return {d: _cache[(a.id, d)] for d in durations if _cache.get((a.id, d))}


@router.get("/metrics/bests")
def bests(
    start: dt.date | None = None,
    end: dt.date | None = None,
    durations: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Beste Durchschnittsleistung je Dauer im Zeitraum (ohne Angabe: gesamte Zeit) mit Einordnung nach W/kg."""
    try:
        ds = tuple(dict.fromkeys(int(x) for x in durations.split(","))) if durations else DEFAULT_DURATIONS
    except ValueError:
        raise HTTPException(422, "Dauern als kommagetrennte Sekunden angeben")
    if not ds or len(ds) > MAX_DURATIONS or any(not 1 <= d <= 86400 for d in ds):
        raise HTTPException(422, f"Hoechstens {MAX_DURATIONS} Dauern zwischen 1 s und 24 h")
    q = select(Activity).where(Activity.user_id == user.id, Activity.avg_power.is_not(None)).options(defer(Activity.streams))
    if start:
        q = q.where(Activity.start_time >= dt.datetime.combine(start, dt.time.min))
    if end:
        q = q.where(Activity.start_time < dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min))
    best: dict[int, tuple[dict, Activity]] = {}
    for a in db.scalars(q):
        if not is_cycling(a.sport):
            continue
        for d, p in _best_of(a, ds).items():
            if d not in best or p["watts"] > best[d][0]["watts"]:
                best[d] = (p, a)
    weight = user.profile.weight_kg
    out = []
    for d in sorted(ds):
        if d not in best:
            continue
        p, a = best[d]
        wkg = p["watts"] / weight if weight else None
        level = classify(d, wkg) if wkg else None
        out.append({
            "duration_s": d, "watts": round(p["watts"]), "wkg": round(wkg, 2) if wkg else None,
            "level": level, "level_label": LEVEL_LABELS.get(level), "date": a.start_time.date().isoformat(),
            "activity_id": a.id, "activity_name": a.name, "start_s": p["start_s"],
        })
    return {"weight_kg": weight, "ftp": user.profile.ftp, "efforts": out}
