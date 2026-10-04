"""Saisonplan (ATP): Lesen und manuelles Bearbeiten durch den Athleten. Der Coach nutzt dieselbe Logik ueber seine Werkzeuge."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import atp
from ..db import get_db
from ..models import User
from ..security import current_user

router = APIRouter(prefix="/atp", tags=["atp"])


class WeekIn(BaseModel):
    week_start: dt.date
    phase: str
    tss_target: float
    hours_target: float | None = None
    recovery: bool = False
    note: str | None = None


class WeeksIn(BaseModel):
    weeks: list[WeekIn] = Field(min_length=1, max_length=atp.MAX_WEEKS_PER_CALL)


class EventIn(BaseModel):
    name: str
    date: dt.date
    priority: str = "B"
    notes: str | None = None


def _bad(e: atp.AtpError) -> HTTPException:
    return HTTPException(422, str(e))


def _event_out(e) -> dict:
    return {"id": e.id, "date": e.date.isoformat(), "name": e.name, "priority": e.priority, "notes": e.notes}


@router.get("")
def get_plan(start: dt.date | None = None, end: dt.date | None = None,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Lueckenlose Wochenliste (Plan, Soll/Ist-Last, CTL/TSB) und Events. Ohne Datum: vier Wochen zurueck bis 52 voraus."""
    today = dt.date.today()
    start = start or atp.monday_of(today) - dt.timedelta(weeks=4)
    end = end or atp.monday_of(today) + dt.timedelta(weeks=52)
    if end < start or (end - start).days > 110 * 7:
        raise HTTPException(422, "end muss nach start liegen, hoechstens 110 Wochen")
    return atp.get_plan(db, user.id, start, end, today)


@router.put("/weeks")
def put_weeks(body: WeeksIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        starts = atp.upsert_weeks(db, user.id, [w.model_dump(mode="json") for w in body.weeks])
    except atp.AtpError as e:
        raise _bad(e)
    return {"saved": len(starts)}


@router.delete("/weeks")
def delete_weeks(start: dt.date, end: dt.date, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"deleted": atp.clear_weeks(db, user.id, start, end)}


@router.post("/events")
def post_event(body: EventIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return _event_out(atp.save_event(db, user.id, body.model_dump(mode="json")))
    except atp.AtpError as e:
        raise _bad(e)


@router.put("/events/{event_id}")
def put_event(event_id: int, body: EventIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        return _event_out(atp.save_event(db, user.id, {**body.model_dump(mode="json"), "id": event_id}))
    except atp.AtpError as e:
        raise HTTPException(404 if "nicht gefunden" in str(e) else 422, str(e))


@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        atp.delete_event(db, user.id, event_id)
    except atp.AtpError as e:
        raise HTTPException(404, str(e))
