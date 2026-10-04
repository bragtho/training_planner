"""Claude-Coach: Tool-Schleife gegen die Anthropic Messages API.

Pro Anfrage laeuft eine Schleife, bis das Modell keine Werkzeuge mehr aufruft. Der Verlauf
zwischen Anfragen besteht nur aus Text (ohne Tool-Zwischenschritte): Das Modell holt sich
aktuelle Daten ueber die Werkzeuge neu.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics.fitness import current_status, pmc_rows, weekly_summary
from ..models import User
from . import tools as T

log = logging.getLogger(__name__)

MAX_ROUNDS = 10  # Obergrenze fuer Tool-Runden je Anfrage (Kosten-/Endlosschleifen-Schutz)
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

SYSTEM_PROMPT = """Du bist der persoenliche Radtrainer des Athleten in dieser App und ersetzt einen menschlichen Coach. \
Du sprichst Deutsch, per Du, freundlich, direkt und konkret. Du arbeitest nach dem Leistungsmodell von Coggan/TrainingPeaks: \
Trainingszonen in % der FTP, Belastung als TSS, Fitness CTL (42 Tage), Muedigkeit ATL (7 Tage), Form TSB = CTL - ATL.

# Arbeitsweise
- Zahlen und Fakten ueber den Athleten holst Du ausschliesslich ueber die Werkzeuge. Erfinde nie Trainingsdaten. \
Der Kontext unten ist nur eine Momentaufnahme; bei Fragen zu Details oder vor einer Planung rufst Du die Werkzeuge auf.
- Fehlen fuer eine Planung wichtige Angaben (Ziel bzw. Ziel-Event mit Datum, verfuegbare Zeit je Woche, aktuelle FTP), \
frage knapp nach, statt zu raten. Speichere genannte Ziele und Verfuegbarkeit mit update_athlete_notes. \
Bei kleinen Anfragen (z. B. "plane mir morgen etwas Lockeres") handelst Du sofort.
- Wenn der Athlet einen Plan oder eine Aenderung will, schreibst Du sie selbst in den Kalender (create_workouts / update_workout / delete_workout). \
Beschreibe danach kurz, was Du geplant hast (Tage, Dauer, TSS) und warum.
- Lies nach dem Anlegen den Wochenlast-Check im Ergebnis. Bei einer Warnung korrigierst Du den Plan, bevor Du antwortest.
- Beurteilst Du Training, vergleichst Du Soll und Ist (get_calendar, get_recent_activities) und erklaerst die Ursache in einem Satz, \
bevor Du anpasst. Ein verpasstes Training holst Du nicht pauschal nach.

# Trainingsregeln
- Periodisierung: Belastungswochen und Entlastungswoche, typisch 3:1 (Entlastungswoche ca. 60-70 % der Last). \
Der CTL soll im Aufbau um etwa 3-6 Punkte pro Woche steigen, selten mehr. Als Referenz fuer eine Wochenlast dient etwa 7 x CTL.
- Eine Woche hat mindestens 1 Ruhetag und hoechstens 2-3 intensive Einheiten (Schwelle und darueber), nie zwei harte Tage direkt nacheinander. \
Der Rest ist Grundlage (Z2). Halte die genannte Verfuegbarkeit ein.
- Vor einem wichtigen Event nimmst Du die Last in den letzten 7-14 Tagen zurueck (Tapering), die Intensitaet bleibt, das Volumen sinkt.
- TSB: etwa -10 bis -30 im Aufbau ist normal; unter -30 droht Ueberlastung, dann Last senken. Form fuer ein Event: etwa +5 bis +20.
- Trainings legst Du nur ab heute an. Du loeschst oder aenderst nichts ohne Anlass und aenderst keine absolvierten Trainings.

# Struktur eines Trainings
Ablauf als Liste von Schritten (siehe Werkzeugbeschreibung): warmup/cooldown als Rampe von-bis, steady/interval/rest konstant, \
Intervalle als Wiederholungsgruppe. Typische Bereiche in % FTP: Erholung 45-55, Grundlage 56-75, Tempo 76-90, Sweetspot 88-94, \
Schwelle 95-105, VO2max 106-120, Anaerob 121-150. Jedes Training mit Ablauf beginnt mit Aufwaermen und endet mit Ausfahren. \
Freie Ausfahrten ohne Struktur gehen mit planned_duration_s und planned_tss.

# Grenzen
- Du bist kein Arzt. Bei Schmerzen in der Brust, Atemnot, Schwindel, Verletzungen, Herz-Kreislauf-Beschwerden oder anhaltender Erschoepfung \
rate Du zu Pause und aerztlicher Abklaerung und plane nichts Intensives. Keine Diagnosen, keine Medikamente, keine Diaeten.
- Die FTP und Herzfrequenzwerte aenderst Du nicht selbst; Du kannst einen FTP-Test oder neue Werte vorschlagen.
- TSS-Werte aus Strava ohne Powermeter sind Schaetzungen. Weise bei grossen Unsicherheiten darauf hin.

# Antwortstil
Kurz und klar. Nutze kurze Absaetze oder Listen, keine Ueberschriften. Nenne konkrete Zahlen (Watt, Minuten, TSS). \
Wiederhole nicht, was in den Werkzeugergebnissen steht, sondern ordne es ein."""


class CoachError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def build_context(db: Session, user: User, today: dt.date | None = None) -> str:
    """Momentaufnahme fuer den (nicht gecachten) zweiten Systemblock."""
    today = today or dt.date.today()
    p = user.profile
    rows = pmc_rows(db, user.id, today)
    cur = current_status(rows)
    lines = [f"Heute ist {WEEKDAY_NAMES[today.weekday()]}, der {today.isoformat()}.", "", "Athlet:",
             f"- FTP {p.ftp:.0f} W" + (f", Gewicht {p.weight_kg:.0f} kg" if p.weight_kg else ""),
             f"- Puls: max {p.hr_max or '?'}, Ruhe {p.hr_rest or '?'}, Schwelle {p.lthr or '?'}",
             f"- Ziele: {p.goals or 'nicht angegeben'}",
             f"- Verfuegbarkeit (Minuten je Wochentag): {json.dumps(p.availability) if p.availability else 'nicht angegeben'}"]
    if cur:
        lines += ["", f"Aktuell: CTL {cur['ctl']}, ATL {cur['atl']}, TSB {cur['tsb']}, CTL-Anstieg 7 Tage {cur['ramp_rate']}",
                  "TSS je Woche (aelteste zuerst): " + ", ".join(str(w["tss"]) for w in weekly_summary(db, user.id, 6, today))]
    else:
        lines += ["", "Es liegen noch keine Trainingsdaten mit TSS vor."]
    return "\n".join(lines)


def _client(settings=None) -> anthropic.Anthropic:
    s = settings or get_settings()
    if not s.anthropic_api_key:
        raise CoachError("ANTHROPIC_API_KEY fehlt in backend/.env", 503)
    return anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=2)


def _stream(client: Any, kwargs: dict, use_fallback: bool):
    """Ein Modellaufruf (gestreamt gegen HTTP-Timeouts, wir brauchen nur die fertige Nachricht)."""
    if use_fallback:
        # Wird eine Anfrage von den Sicherheitsfiltern abgelehnt, uebernimmt serverseitig ein Ersatzmodell
        with client.beta.messages.stream(**kwargs, betas=[FALLBACK_BETA], fallbacks="default") as stream:
            return stream.get_final_message()
    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message()


def run_coach(
    db: Session,
    user: User,
    text: str,
    history: list[dict],
    *,
    model: str,
    effort: str = "medium",
    client: Any = None,
) -> dict:
    """Fuehrt eine Coach-Anfrage aus. history: [{"role","content": str}] (nur Text).

    Rueckgabe: {"text": str, "actions": [str], "model": str}
    """
    settings = get_settings()
    client = client or _client(settings)
    system = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": build_context(db, user)},
    ]
    messages: list[dict] = [*history, {"role": "user", "content": text}]
    actions: list[str] = []
    use_fallback = settings.coach_refusal_fallback
    final = None

    for _ in range(MAX_ROUNDS):
        kwargs = dict(
            model=model, max_tokens=MAX_TOKENS, system=system, tools=T.TOOLS, messages=messages,
            thinking={"type": "adaptive"}, output_config={"effort": effort},
        )
        try:
            try:
                final = _stream(client, kwargs, use_fallback)
            except anthropic.BadRequestError as e:
                # Faellt die Fallback-Option aus (z. B. nicht freigeschaltet), ohne sie erneut versuchen
                if not (use_fallback and "fallback" in str(e).lower()):
                    raise
                log.warning("Fallback-Parameter abgelehnt, wiederhole ohne: %s", e)
                use_fallback = False
                final = _stream(client, kwargs, False)
        except anthropic.AuthenticationError:
            raise CoachError("Der Anthropic-API-Key wurde abgelehnt. Bitte ANTHROPIC_API_KEY pruefen.", 503)
        except anthropic.RateLimitError:
            raise CoachError("Anthropic-Limit erreicht, bitte in einer Minute erneut versuchen.", 429)
        except anthropic.APIConnectionError:
            raise CoachError("Keine Verbindung zur Anthropic-API.", 502)
        except anthropic.APIStatusError as e:
            log.error("Anthropic-Fehler %s: %s", e.status_code, e)
            raise CoachError(f"Anthropic-Fehler ({e.status_code}).", 502)

        if final.stop_reason == "refusal":
            return {"text": "Dazu kann ich Dir leider nicht helfen. Formuliere die Frage gern anders.",
                    "actions": actions, "model": model}

        # Antwort unveraendert (inkl. Thinking-Bloecke) in den Verlauf dieser Anfrage uebernehmen
        messages.append({"role": "assistant", "content": final.content})
        if final.stop_reason == "pause_turn":
            continue
        uses = [b for b in final.content if b.type == "tool_use"]
        if final.stop_reason == "max_tokens" or not uses:
            break

        results = []
        for block in uses:
            handler = T.HANDLERS.get(block.name)
            try:
                if handler is None:
                    raise T.ToolError(f"Unbekanntes Werkzeug '{block.name}'")
                if not isinstance(block.input, dict):
                    raise T.ToolError("Eingabe muss ein JSON-Objekt sein")
                result = handler(db, user, block.input)
                if block.name in T.WRITE_TOOLS:
                    actions.append(T.action_summary(block.name, block.input, result))
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False)})
            except T.ToolError as e:
                db.rollback()
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True, "content": str(e)})
            except Exception:  # Fehler im Werkzeug darf die Konversation nicht abbrechen
                log.exception("Werkzeug %s fehlgeschlagen", block.name)
                db.rollback()
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": "Interner Fehler im Werkzeug."})
        messages.append({"role": "user", "content": results})
    else:
        final = None  # Rundenlimit erreicht, ohne dass das Modell fertig wurde

    answer = "".join(b.text for b in final.content if b.type == "text").strip() if final else ""
    if final is not None and final.stop_reason == "max_tokens":
        answer = (answer + "\n\n(Antwort wurde wegen der Laenge abgebrochen. Frag gern nach.)").strip()
    if not answer:
        answer = "Ich konnte die Anfrage nicht abschliessen. Bitte versuche es noch einmal."
        if actions:
            answer += " Bereits ausgefuehrt: " + "; ".join(actions) + "."
    return {"text": answer, "actions": actions, "model": model}
