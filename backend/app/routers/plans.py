import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..metrics.workout import Steps, summarize
from ..models import Activity, PlannedWorkout, User
from ..routers.activities import ActivityOut, _out as activity_out
from ..security import current_user

router = APIRouter(tags=["plans"])

MAX_RANGE_DAYS = 100


class WorkoutIn(BaseModel):
    date: dt.date
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)
    structure: Steps | None = None
    # Nur ohne Struktur (z. B. "Ruhetag" oder freies Training); mit Struktur wird beides berechnet
    planned_duration_s: int | None = Field(None, ge=0, le=86400)
    planned_tss: float | None = Field(None, ge=0, le=1000)
    status: Literal["planned", "skipped"] = "planned"


class WorkoutOut(BaseModel):
    id: int
    date: dt.date
    title: str
    description: str | None
    structure: list | None
    planned_duration_s: int | None
    planned_tss: float | None
    # planned | completed | missed | skipped (completed/missed werden aus den Aktivitaeten abgeleitet)
    status: str
    created_by: str
    activity_id: int | None = None
    actual_tss: float | None = None


class PreviewIn(BaseModel):
    structure: Steps


def _apply(w: PlannedWorkout, body: WorkoutIn, ftp: float) -> None:
    w.date = body.date
    w.title = body.title.strip()
    w.description = body.description
    w.status = body.status
    if body.structure:
        s = summarize(body.structure, ftp)
        w.structure = [step.model_dump() for step in body.structure]
        w.planned_duration_s = s["duration_s"]
        w.planned_tss = s["tss"]
    else:
        w.structure = None
        w.planned_duration_s = body.planned_duration_s
        w.planned_tss = body.planned_tss


def _serialize(w: PlannedWorkout, act: Activity | None, today: dt.date) -> WorkoutOut:
    if w.status == "skipped":
        status = "skipped"
    elif act is not None:
        status = "completed"
    elif w.date < today:
        status = "missed"
    else:
        status = "planned"
    return WorkoutOut(
        id=w.id, date=w.date, title=w.title, description=w.description, structure=w.structure,
        planned_duration_s=w.planned_duration_s, planned_tss=w.planned_tss, status=status,
        created_by=w.created_by, activity_id=act.id if act else None, actual_tss=act.tss if act else None,
    )


def _get(db: Session, user: User, workout_id: int) -> PlannedWorkout:
    w = db.get(PlannedWorkout, workout_id)
    if w is None or w.user_id != user.id:
        raise HTTPException(404, "Training nicht gefunden")
    return w


def _day_activity(db: Session, user: User, day: dt.date, taken: set[int]) -> Activity | None:
    start = dt.datetime.combine(day, dt.time.min)
    rows = db.scalars(
        select(Activity)
        .where(Activity.user_id == user.id, Activity.start_time >= start, Activity.start_time < start + dt.timedelta(days=1))
        .order_by(Activity.start_time)
    )
    return next((a for a in rows if a.id not in taken), None)


def calendar_data(db: Session, user: User, start: dt.date, end: dt.date) -> tuple[list[WorkoutOut], list[Activity]]:
    """Geplante Trainings (mit abgeleitetem Status) und Aktivitaeten eines Zeitraums."""
    t0 = dt.datetime.combine(start, dt.time.min)
    t1 = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min)
    acts = list(
        db.scalars(
            select(Activity)
            .where(Activity.user_id == user.id, Activity.start_time >= t0, Activity.start_time < t1)
            .order_by(Activity.start_time)
        )
    )
    by_day: dict[dt.date, list[Activity]] = {}
    for a in acts:
        by_day.setdefault(a.start_time.date(), []).append(a)
    workouts = db.scalars(
        select(PlannedWorkout)
        .where(PlannedWorkout.user_id == user.id, PlannedWorkout.date >= start, PlannedWorkout.date <= end)
        .order_by(PlannedWorkout.date, PlannedWorkout.id)
    )
    today = dt.date.today()
    taken: set[int] = set()
    out = []
    for w in workouts:
        # pro Tag wird jede Aktivitaet hoechstens einem Workout zugeordnet
        match = next((a for a in by_day.get(w.date, []) if a.id not in taken and w.status != "skipped"), None)
        if match:
            taken.add(match.id)
        out.append(_serialize(w, match, today))
    return out, acts


@router.get("/calendar")
def calendar(start: dt.date, end: dt.date, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(422, f"Zeitraum ungueltig (max. {MAX_RANGE_DAYS} Tage)")
    workouts, acts = calendar_data(db, user, start, end)
    return {"workouts": workouts, "activities": [activity_out(a) for a in acts]}


@router.post("/workouts/preview")
def preview(body: PreviewIn, user: User = Depends(current_user)):
    return summarize(body.structure, user.profile.ftp)


@router.post("/workouts", response_model=WorkoutOut, status_code=201)
def create_workout(body: WorkoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = PlannedWorkout(user_id=user.id, created_by="user")
    _apply(w, body, user.profile.ftp)
    db.add(w)
    db.commit()
    return _serialize(w, None, dt.date.today())


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
def get_workout(workout_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _get(db, user, workout_id)
    return _serialize(w, _day_activity(db, user, w.date, set()), dt.date.today())


@router.put("/workouts/{workout_id}", response_model=WorkoutOut)
def update_workout(
    workout_id: int, body: WorkoutIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    w = _get(db, user, workout_id)
    _apply(w, body, user.profile.ftp)
    db.commit()
    return _serialize(w, _day_activity(db, user, w.date, set()), dt.date.today())


@router.delete("/workouts/{workout_id}", status_code=204)
def delete_workout(workout_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_get(db, user, workout_id))
    db.commit()


@router.post("/workouts/{workout_id}/copy", response_model=WorkoutOut, status_code=201)
def copy_workout(
    workout_id: int, date: dt.date, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    src = _get(db, user, workout_id)
    w = PlannedWorkout(
        user_id=user.id, date=date, title=src.title, description=src.description, structure=src.structure,
        planned_duration_s=src.planned_duration_s, planned_tss=src.planned_tss, created_by="user",
    )
    db.add(w)
    db.commit()
    return _serialize(w, None, dt.date.today())
