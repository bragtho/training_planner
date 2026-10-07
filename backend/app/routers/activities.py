from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations import strava
from ..metrics.fitness import current_status, pmc_rows
from ..metrics.power import intensity_factor, mean_max_curve, tss
from ..models import Activity, ActivityInsight, Integration, User
from ..security import current_user

router = APIRouter(tags=["activities"])

MAX_STREAM_POINTS = 600
CURVE_DURATIONS = (1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 480, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200,
                   10800, 14400, 21600)


class ActivityOut(BaseModel):
    id: int
    source: str
    name: str | None
    sport: str
    start_time: datetime
    duration_s: int
    distance_m: float
    elevation_m: float | None
    avg_power: float | None
    norm_power: float | None
    avg_hr: float | None
    intensity_factor: float | None
    tss: float | None
    has_streams: bool
    feedback_headline: str | None = None


def _out(a: Activity) -> ActivityOut:
    return ActivityOut(
        id=a.id, source=a.source, name=a.name, sport=a.sport, start_time=a.start_time,
        duration_s=a.duration_s, distance_m=a.distance_m, elevation_m=a.elevation_m,
        avg_power=a.avg_power, norm_power=a.norm_power, avg_hr=a.avg_hr,
        intensity_factor=a.intensity_factor, tss=a.tss, has_streams=bool(a.streams),
    )


def _get(db: Session, user: User, activity_id: int) -> Activity:
    a = db.get(Activity, activity_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Aktivitaet nicht gefunden")
    return a


@router.get("/activities", response_model=list[ActivityOut])
def list_activities(
    limit: int = 30, offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(
        select(Activity)
        .where(Activity.user_id == user.id)
        .order_by(Activity.start_time.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
    )
    acts = list(rows)
    headlines = dict(db.execute(select(ActivityInsight.activity_id, ActivityInsight.feedback)
                                .where(ActivityInsight.activity_id.in_([a.id for a in acts]),
                                       ActivityInsight.feedback.is_not(None))).all()) if acts else {}
    out = []
    for a in acts:
        o = _out(a)
        o.feedback_headline = (headlines.get(a.id) or {}).get("headline")
        out.append(o)
    return out


@router.get("/activities/{activity_id}", response_model=ActivityOut)
def get_activity(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_get(db, user, activity_id))


def _downsample(values: list, step: int) -> list:
    return values[::step] if step > 1 else values


@router.get("/activities/{activity_id}/streams")
def get_streams(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Streams (Watt, Puls, ...). Werden beim ersten Aufruf von Strava geholt; berechnet NP/TSS exakt neu."""
    a = _get(db, user, activity_id)
    if not a.streams:
        if a.source != "strava":
            raise HTTPException(404, "Keine Streams vorhanden")
        integ = db.scalar(select(Integration).where(Integration.user_id == user.id, Integration.provider == "strava"))
        if integ is None:
            raise HTTPException(409, "Strava ist nicht verbunden")
        try:
            streams = strava.StravaClient(db, integ).get_streams(a.external_id)
        except strava.StravaError as e:
            raise HTTPException(e.status if e.status in (401, 404, 429) else 502, str(e))
        strava.apply_streams(a, streams, user.profile)
        db.commit()
    elif "latlng" not in a.streams and a.source == "strava":
        # Aeltere Aktivitaet ohne Kartendaten: GPS einmal nachladen (NP/TSS bleiben unveraendert)
        integ = db.scalar(select(Integration).where(Integration.user_id == user.id, Integration.provider == "strava"))
        if integ is not None:
            try:
                gps = strava.StravaClient(db, integ).get_streams(a.external_id).get("latlng") or []
            except strava.StravaError:
                gps = None  # spaeter erneut versuchen
            if gps is not None:
                a.streams = {**a.streams, "latlng": gps}
                db.commit()
    n = max((len(v) for v in a.streams.values()), default=0)
    step = max(1, -(-n // MAX_STREAM_POINTS))
    return {k: _downsample(v, step) for k, v in a.streams.items()}


@router.get("/activities/{activity_id}/power-curve")
def get_power_curve(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Leistungskurve dieser Fahrt: beste Durchschnittsleistung je Dauer und wo sie gefahren wurde (Startsekunde)."""
    a = _get(db, user, activity_id)
    s = a.streams or {}
    watts = strava.resample_1hz(s.get("time") or [], s.get("watts") or [])
    return {"points": mean_max_curve(watts, CURVE_DURATIONS)}


@router.get("/metrics/pmc")
def pmc(days: int = 180, user: User = Depends(current_user), db: Session = Depends(get_db)):
    days = min(max(days, 7), 1500)
    all_rows = pmc_rows(db, user.id)
    if not all_rows:
        return {"rows": [], "current": None}
    cutoff = all_rows[-1]["date"] - timedelta(days=days - 1)
    return {
        "rows": [
            {"date": r["date"].isoformat(), "tss": round(r["tss"], 1), "ctl": round(r["ctl"], 1),
             "atl": round(r["atl"], 1), "tsb": round(r["tsb"], 1)}
            for r in all_rows if r["date"] >= cutoff
        ],
        "current": current_status(all_rows),
    }


@router.post("/metrics/recompute")
def recompute(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Berechnet TSS aller Aktivitaeten mit der aktuellen FTP neu (nach FTP-Aenderung)."""
    ftp = user.profile.ftp
    n = 0
    for a in db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.norm_power.is_not(None))):
        a.intensity_factor = intensity_factor(a.norm_power, ftp)
        a.tss = tss(a.duration_s, a.norm_power, ftp)
        a.ftp_used = ftp
        n += 1
    db.commit()
    return {"recomputed": n}
