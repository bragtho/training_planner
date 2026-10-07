"""Analyse von Training und Rennen: Auswertung je Fahrt, Coach-Feedback, Belastungs- und FTP-Pruefung."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import insights as I
from ..config import get_settings
from ..db import get_db
from ..metrics.sports import is_cycling
from ..models import Activity, User
from ..security import current_user

router = APIRouter(tags=["insights"])


def _activity(db: Session, user: User, activity_id: int) -> Activity:
    a = db.get(Activity, activity_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Aktivitaet nicht gefunden")
    return a


@router.get("/activities/{activity_id}/analysis")
def analysis(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Auswertung einer Fahrt (laedt fehlende Sensordaten bei Strava) samt gespeichertem Feedback des Coaches."""
    act = _activity(db, user, activity_id)
    if not is_cycling(act.sport):
        return {"supported": False, "sport": act.sport}  # Auswertung und Feedback gibt es nur fuer Radtrainings
    report = I.activity_report(db, user, act)
    row = I.insight_row(db, act)
    db.commit()
    return {**report, "feedback": row.feedback, "feedback_status": row.feedback_status,
            "coach_configured": bool(get_settings().anthropic_api_key)}


@router.post("/activities/{activity_id}/feedback")
def feedback(activity_id: int, force: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Feedback des Coaches zu einer Fahrt erzeugen (oder das gespeicherte liefern; force erzeugt es neu)."""
    act = _activity(db, user, activity_id)
    try:
        return {"feedback": I.generate_feedback(db, user, act, force=force)}
    except I.InsightError as e:
        raise HTTPException(e.status, str(e))


@router.get("/metrics/load-check")
def load_check(coach: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ist die Trainingsbelastung zu hoch, passend oder zu gering? coach=true ergaenzt die Einordnung des Coaches
    (beruecksichtigt Gedaechtnis und Gespraech, z. B. eine Offseason); sie fehlt ohne Coach oder bei Fehlern."""
    report = I.load_report(db, user)
    if coach:
        report["coach"] = I.coach_load_view(db, user, report)
    return report


@router.get("/metrics/ftp-check")
def ftp_check(refresh: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Pruefung, ob die eingestellte FTP zu den Leistungen passt. refresh laedt Sensordaten harter Fahrten nach."""
    return I.ftp_report(db, user, backfill=I.BACKFILL_DEFAULT if refresh else 0)


class FtpIn(BaseModel):
    ftp: float = Field(gt=50, lt=700)


@router.post("/metrics/ftp-check/accept")
def accept_ftp(body: FtpIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Uebernimmt eine neue FTP (Vorschlag der Pruefung) und berechnet TSS, IF und Analysen neu."""
    old = user.profile.ftp
    I.set_ftp(db, user, body.ftp, source="user", reason="Vorschlag der FTP-Pruefung uebernommen")
    return {"old_ftp": old, "ftp": user.profile.ftp, "recomputed": I.recompute_tss(db, user)}
