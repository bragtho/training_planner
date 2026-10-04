"""Kurzer Formhinweis fuer die Uebersicht, der Gespraech, Ziele und Kalender beruecksichtigt.

Die Einordnung des TSB-Werts allein (z. B. "lange Pause") kann dem widersprechen, was mit dem Coach
vereinbart wurde (Offseason, Verletzung, Urlaub). Deshalb schreibt das Modell den Hinweis auf Basis
des Gespraechs. Ohne Kontext oder bei Fehlern gibt es None, die App zeigt dann ihre Standardtexte.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import threading
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics.fitness import current_status, pmc_rows
from ..models import CoachMessage, PlannedWorkout, User
from .agent import WEEKDAY_NAMES, _client, _stream, build_context
from .tools import active_memories, memory_line

log = logging.getLogger(__name__)

CHAT_MESSAGES = 12  # so viel Gespraech fliesst ein
CHAT_CHARS = 700  # je Nachricht, damit lange Plaene den Prompt nicht aufblaehen
UPCOMING_DAYS = 14
MAX_LEN = 280
MAX_TOKENS = 4000  # grosszuegig: bezahlt wird nur, was erzeugt wird; der Text selbst braucht ~100

SYSTEM_PROMPT = """Du bist der persoenliche Radtrainer des Athleten. Schreibe fuer die Uebersichtsseite der App einen kurzen Hinweis \
zur aktuellen Form (TSB). Deutsch, per Du (Du, Dein und Dich gross geschrieben), freundlich und konkret, hoechstens zwei Saetze und {max_len} Zeichen, kein Markdown, keine Anrede.

Regeln:
- Beruecksichtige ausdruecklich, was im Gedaechtnis, im gerade gefuehrten Gespraech und in den Zielen steht: Saisonphase (z. B. Offseason), \
Pausen, Verletzungen, Urlaub, Trainingsbeginn, Events. Der Hinweis darf dem Gespraech nie widersprechen.
- Ist die Form hoch, weil der Athlet bewusst pausiert, sag das als normal und gewollt, statt zum Training zu draengen.
- Nenne Daten nur so, wie sie im Gespraech stehen (z. B. "bis zum ersten Montag im November"). Rechne keine Kalendertage aus und \
erfinde keine Termine, Zahlen oder Plaene.
- Steht im Gespraech nichts, was die Form betrifft, gib einen allgemeinen Hinweis zu dieser Form.
- Die App zeigt darueber schon die Einordnung (Ueberlastet, Produktiv, Ausgeglichen, Frisch, Sehr erholt) und die Zahl. Wiederhole sie nicht.

Einordnung des TSB: unter -30 hohe Ermuedung; -30 bis -10 produktiver Aufbau; -10 bis +5 ausgeglichen; +5 bis +25 frisch; \
ueber +25 sehr erholt (die Fitness sinkt, wenn laenger nicht trainiert wird)."""

_lock = threading.Lock()
_cache: dict[int, tuple[tuple, str]] = {}


def _clean(text: str) -> str:
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_LEN:
        cut = text[:MAX_LEN]
        # am letzten Satzende kuerzen, sonst hart abschneiden
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[: end + 1] if end > MAX_LEN // 2 else cut.rstrip() + "…"
    return text


def _chat_lines(db: Session, user: User) -> tuple[list[str], int]:
    rows = list(db.scalars(
        select(CoachMessage).where(CoachMessage.user_id == user.id).order_by(CoachMessage.id.desc()).limit(CHAT_MESSAGES)
    ))[::-1]
    lines = []
    for r in rows:
        t = (r.content.get("text", "") if isinstance(r.content, dict) else str(r.content)).strip()
        if t:
            who = "Athlet" if r.role == "user" else "Coach"
            lines.append(f"{who}: {t[:CHAT_CHARS]}")
    return lines, (rows[-1].id if rows else 0)


def _upcoming(db: Session, user: User, today: dt.date) -> list[str]:
    rows = db.scalars(
        select(PlannedWorkout).where(
            PlannedWorkout.user_id == user.id, PlannedWorkout.status == "planned",
            PlannedWorkout.date >= today, PlannedWorkout.date <= today + dt.timedelta(days=UPCOMING_DAYS),
        ).order_by(PlannedWorkout.date)
    )
    return [f"{WEEKDAY_NAMES[w.date.weekday()]} {w.date.isoformat()}: {w.title}" for w in rows]


def form_hint(db: Session, user: User, *, client: Any = None, today: dt.date | None = None) -> str | None:
    """Hinweistext oder None (kein Kontext, nicht eingerichtet oder Fehler)."""
    settings = get_settings()
    if client is None and not settings.anthropic_api_key:
        return None
    today = today or dt.date.today()
    chat, last_id = _chat_lines(db, user)
    goals = user.profile.goals or ""
    memories = tuple(memory_line(m) for m in active_memories(db, user.id, today))
    if not chat and not goals.strip() and not memories:
        return None  # nichts, was ueber die Standardeinordnung hinausgeht
    upcoming = _upcoming(db, user, today)
    cur = current_status(pmc_rows(db, user.id, today))
    if not cur:
        return None

    # Gleicher Zustand, gleicher Text: kein erneuter Modellaufruf bei jedem Oeffnen der Seite
    key = (today, last_id, goals, round(cur["tsb"]), tuple(upcoming), memories)
    with _lock:
        hit = _cache.get(user.id)
        if hit and hit[0] == key:
            return hit[1]

        prompt = "\n".join([
            build_context(db, user, today), "",
            f"Geplante Trainings in den naechsten {UPCOMING_DAYS} Tagen: " + ("; ".join(upcoming) if upcoming else "keine"), "",
            "Letzter Teil des Gespraechs (aelteste zuerst):",
            *(chat or ["(noch kein Gespraech)"]), "",
            "Schreibe jetzt den Hinweis zur aktuellen Form.",
        ])
        try:
            final = _stream(client or _client(settings), dict(
                model=settings.coach_chat_model, max_tokens=MAX_TOKENS, thinking={"type": "between_tools"},  # schaltet das Nachdenken bei diesem Modell aus ("disabled" wird abgelehnt)
                system=SYSTEM_PROMPT.format(max_len=MAX_LEN),
                messages=[{"role": "user", "content": prompt}],
            ), False)
        except (anthropic.APIError, OSError) as e:
            log.warning("Formhinweis nicht erzeugt: %s", e)
            return None
        text = _clean("".join(b.text for b in final.content if b.type == "text"))
        if final.stop_reason == "refusal":
            return None
        if final.stop_reason == "max_tokens":
            # Abgebrochen: nur bis zum letzten vollstaendigen Satz behalten, einen halben Satz nie anzeigen
            log.warning("Formhinweis wegen Tokenlimit gekuerzt")
            end = max(text.rfind(". "), text.rfind("! "), text.rfind("? "), text.rfind(".") if text.endswith(".") else -1)
            text = text[: end + 1] if end > 0 else ""
        if not text:
            return None
        _cache[user.id] = (key, text)
        return text
