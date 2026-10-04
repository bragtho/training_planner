import datetime as dt
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..coach.agent import CoachError, run_coach
from ..coach.form_hint import form_hint
from ..config import get_settings
from ..db import get_db
from ..coach.tools import active_memories
from ..models import CoachMemory, CoachMessage, User
from ..security import current_user

router = APIRouter(prefix="/coach", tags=["coach"])

HISTORY_MESSAGES = 20
MAX_TEXT = 4000

QUICK_PROMPTS = {
    "plan_week": (
        "Plane meine Trainingswoche. Schau Dir zuerst meinen aktuellen Zustand, die letzten Wochen und meinen Kalender an. "
        "Plane die Trainingstage ab heute bis zum kommenden Sonntag; sind es weniger als drei Tage, plane die ganze naechste Woche. "
        "Beruecksichtige meine Ziele und Verfuegbarkeit und lege die Trainings im Kalender an. Fehlt etwas Wesentliches, frag mich zuerst."
    ),
    "review_last": (
        "Werte mein letztes Training aus. Vergleiche es mit dem Plan und meiner aktuellen Form (CTL, ATL, TSB) und sag mir, "
        "was gut war und worauf ich achten soll. Passe die kommenden Tage im Kalender nur an, wenn es wirklich noetig ist."
    ),
}

_running: set[int] = set()
_lock = threading.Lock()


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_TEXT)


class QuickIn(BaseModel):
    action: Literal["plan_week", "review_last"]


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    actions: list[str] = []
    model: str | None = None
    created_at: dt.datetime


def _out(m: CoachMessage) -> MessageOut:
    c = m.content if isinstance(m.content, dict) else {"text": str(m.content)}
    created = m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=dt.timezone.utc)
    return MessageOut(id=m.id, role=m.role, text=c.get("text", ""), actions=c.get("actions", []),
                      model=c.get("model"), created_at=created)


def _history(db: Session, user_id: int) -> list[dict]:
    rows = list(db.scalars(
        select(CoachMessage).where(CoachMessage.user_id == user_id).order_by(CoachMessage.id.desc()).limit(HISTORY_MESSAGES)
    ))[::-1]
    out: list[dict] = []
    for r in rows:
        text = (r.content.get("text", "") if isinstance(r.content, dict) else str(r.content))[:MAX_TEXT]
        if not text:
            continue
        if out and out[-1]["role"] == r.role:  # API verlangt abwechselnde Rollen
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": r.role, "content": text})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _run(db: Session, user: User, text: str, model: str, effort: str) -> list[MessageOut]:
    s = get_settings()
    if not s.anthropic_api_key:
        raise HTTPException(503, "Der Coach ist nicht eingerichtet: ANTHROPIC_API_KEY fehlt in backend/.env")
    midnight = dt.datetime.combine(dt.date.today(), dt.time.min, tzinfo=dt.timezone.utc)
    sent_today = db.scalar(select(func.count()).select_from(CoachMessage).where(
        CoachMessage.user_id == user.id, CoachMessage.role == "user", CoachMessage.created_at >= midnight))
    if (sent_today or 0) >= s.coach_daily_message_limit:
        raise HTTPException(429, "Tageslimit fuer Coach-Nachrichten erreicht")
    with _lock:
        if user.id in _running:
            raise HTTPException(409, "Der Coach arbeitet noch an Deiner letzten Anfrage")
        _running.add(user.id)
    try:
        history = _history(db, user.id)
        try:
            result = run_coach(db, user, text, history, model=model, effort=effort)
        except CoachError as e:
            raise HTTPException(e.status, str(e))
        # Erst nach Erfolg speichern, damit fehlgeschlagene Anfragen keine halben Verlaeufe hinterlassen
        um = CoachMessage(user_id=user.id, role="user", content={"text": text})
        am = CoachMessage(user_id=user.id, role="assistant",
                          content={"text": result["text"], "actions": result["actions"], "model": result["model"]})
        db.add_all([um, am])
        db.commit()
        return [_out(um), _out(am)]
    finally:
        with _lock:
            _running.discard(user.id)


@router.get("/status")
def status(user: User = Depends(current_user)):
    s = get_settings()
    return {"configured": bool(s.anthropic_api_key), "chat_model": s.coach_chat_model,
            "planning_model": s.coach_planning_model}


class MemoryOut(BaseModel):
    id: int
    text: str
    valid_until: dt.date | None = None


@router.get("/memories", response_model=list[MemoryOut])
def memories(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Was sich der Coach ueber den Athleten gemerkt hat (nur gueltige Eintraege)."""
    return [MemoryOut(id=m.id, text=m.text, valid_until=m.valid_until) for m in active_memories(db, user.id)]


@router.delete("/memories/{memory_id}", status_code=204)
def forget(memory_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(CoachMemory, memory_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(404, "Eintrag nicht gefunden")
    db.delete(m)
    db.commit()


@router.get("/form-hint")
def form_hint_text(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Formhinweis fuer die Uebersicht, abgestimmt auf das Gespraech. text ist null, wenn es keinen gibt."""
    return {"text": form_hint(db, user)}


@router.get("/messages", response_model=list[MessageOut])
def messages(limit: int = 60, user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(CoachMessage).where(CoachMessage.user_id == user.id)
                      .order_by(CoachMessage.id.desc()).limit(min(max(limit, 1), 200)))
    return [_out(m) for m in list(rows)[::-1]]


@router.post("/chat", response_model=list[MessageOut])
def chat(body: ChatIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    return _run(db, user, body.message.strip(), s.coach_chat_model, "medium")


@router.post("/quick", response_model=list[MessageOut])
def quick(body: QuickIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = get_settings()
    # Planen ist die anspruchsvollste Aufgabe: staerkeres Modell und hoeherer Aufwand
    if body.action == "plan_week":
        return _run(db, user, QUICK_PROMPTS["plan_week"], s.coach_planning_model, "high")
    return _run(db, user, QUICK_PROMPTS["review_last"], s.coach_chat_model, "medium")


@router.delete("/messages", status_code=204)
def clear(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(CoachMessage).where(CoachMessage.user_id == user.id))
    db.commit()
