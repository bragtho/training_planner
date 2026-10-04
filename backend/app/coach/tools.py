"""Werkzeuge des KI-Coaches: Lesezugriff auf Daten, Schreibzugriff nur auf Trainingsplan und Ziele.

Alle Eingaben stammen vom Modell und werden wie untrusted Input behandelt: Schema-Validierung,
Datumsgrenzen und Mengenlimits sitzen hier, nicht im Prompt.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..metrics.fitness import current_status, pmc_rows, weekly_summary
from ..metrics.power import power_zones
from .. import atp as A
from ..models import Activity, AtpWeek, CoachMemory, PlannedWorkout, User
from ..routers.plans import WorkoutIn, _apply, calendar_data

MAX_CREATE = 21
MAX_HORIZON_DAYS = 120
MAX_MEMORIES = 40
MAX_MEMORY_CHARS = 300
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ToolError(Exception):
    """Fehler, der dem Modell als Ergebnis zurueckgemeldet wird (damit es korrigieren kann)."""


# ------------------------------------------------------------------ Schemas ---

_LEAF = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["warmup", "steady", "interval", "rest", "cooldown"]},
        "duration_s": {"type": "integer", "description": "Dauer in Sekunden (5 bis 43200)"},
        "power_pct": {
            "type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
            "description": "[von, bis] in % der FTP (20-250). Aufwaermen/Ausfahren sind Rampen von->bis, sonst konstant mit dem Mittelwert.",
        },
    },
    "required": ["type", "duration_s", "power_pct"],
}
_REPEAT = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["repeat"]},
        "count": {"type": "integer", "description": "Anzahl Wiederholungen (1-50)"},
        "steps": {"type": "array", "items": _LEAF, "minItems": 1, "maxItems": 10,
                  "description": "Einzelschritte der Gruppe (keine Verschachtelung)"},
    },
    "required": ["type", "count", "steps"],
}
_STEPS = {
    "type": "array", "items": {"anyOf": [_LEAF, _REPEAT]}, "minItems": 1, "maxItems": 60,
    "description": "Ablauf des Trainings. Beispiel Sweetspot: Aufwaermen 15 min 50->75 %, 3x(15 min 90 % + 5 min 55 %), Ausfahren 10 min.",
}
_DATE = {"type": "string", "description": "Datum YYYY-MM-DD"}

TOOLS: list[dict] = [
    {
        "name": "get_athlete_profile",
        "description": "Profil des Athleten: FTP, Herzfrequenzwerte, Gewicht, Ziele, Verfuegbarkeit, Leistungszonen.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_fitness_status",
        "description": "Aktuelle Fitness (CTL), Muedigkeit (ATL), Form (TSB), CTL-Anstieg der letzten 7 Tage und Wochenuebersicht "
                       "(TSS, Stunden, Anzahl Fahrten) der letzten Wochen. Wochenwerte sind kumulierte Ist-Werte.",
        "input_schema": {"type": "object", "properties": {"weeks": {"type": "integer", "description": "Anzahl Wochen (1-26), Standard 8"}}},
    },
    {
        "name": "get_recent_activities",
        "description": "Absolvierte Fahrten der letzten Tage mit Dauer, Distanz, Leistung, NP, IF, TSS, Puls. Neueste zuerst.",
        "input_schema": {"type": "object", "properties": {"days": {"type": "integer", "description": "Zeitraum in Tagen (1-90), Standard 14"}}},
    },
    {
        "name": "get_calendar",
        "description": "Geplante Trainings und deren Status (planned/completed/missed/skipped) fuer einen Zeitraum von max. 100 Tagen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start": _DATE, "end": _DATE,
                "include_structure": {"type": "boolean", "description": "Auch den Ablauf der Trainings liefern (Standard false)"},
            },
            "required": ["start", "end"],
        },
    },
    {
        "name": "create_workouts",
        "description": "Legt neue Trainings im Kalender an (heute oder spaeter, max. 21 pro Aufruf, max. 120 Tage voraus). "
                       "Gibt Soll-TSS je Training und einen Wochenlast-Check zurueck; Warnungen im Check ernst nehmen und ggf. mit update_workout nachbessern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workouts": {
                    "type": "array", "minItems": 1, "maxItems": MAX_CREATE,
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": _DATE,
                            "title": {"type": "string", "description": "Kurzer Titel, z. B. 'Sweetspot 3x15'"},
                            "description": {"type": "string", "description": "Ziel und Hinweise fuer den Athleten (optional)"},
                            "structure": _STEPS,
                            "planned_duration_s": {"type": "integer", "description": "Nur ohne structure (z. B. freie Ausfahrt)"},
                            "planned_tss": {"type": "number", "description": "Nur ohne structure"},
                        },
                        "required": ["date", "title"],
                    },
                }
            },
            "required": ["workouts"],
        },
    },
    {
        "name": "update_workout",
        "description": "Aendert ein geplantes Training (nur heute oder in der Zukunft). Nur uebergebene Felder werden geaendert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"}, "date": _DATE, "title": {"type": "string"}, "description": {"type": "string"},
                "structure": _STEPS, "status": {"type": "string", "enum": ["planned", "skipped"]},
            },
            "required": ["id"],
        },
    },
    {
        "name": "delete_workout",
        "description": "Loescht ein geplantes Training (nur heute oder in der Zukunft).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "update_athlete_notes",
        "description": "Speichert Ziele und/oder woechentliche Verfuegbarkeit des Athleten, wenn er sie im Gespraech nennt. "
                       "FTP und Herzfrequenzwerte darfst du NICHT aendern, schlage Aenderungen nur vor.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goals": {"type": "string", "description": "Ziele, Ziel-Events mit Datum (max. 2000 Zeichen); ersetzt den bisherigen Text"},
                "availability": {
                    "type": "object",
                    "description": "Verfuegbare Minuten je Wochentag, Schluessel mon,tue,wed,thu,fri,sat,sun, Werte 0-600",
                    "additionalProperties": {"type": "integer"},
                },
            },
        },
    },
    {
        "name": "save_memory",
        "description": "Merkt Dir einen dauerhaft relevanten Fakt ueber den Athleten (Vorlieben, Saisonphase, Einschraenkungen, Ausstattung, "
                       "Entscheidungen aus dem Gespraech). Ein Fakt pro Eintrag, ein Satz, mit absoluten Daten statt 'naechste Woche'. "
                       "Mit id aktualisierst Du einen vorhandenen Eintrag (siehe Gedaechtnis im Kontext), statt ein Duplikat anzulegen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": f"Der Fakt, hoechstens {MAX_MEMORY_CHARS} Zeichen"},
                "valid_until": {**_DATE, "description": "Nur fuer zeitlich begrenzte Fakten (z. B. Offseason): letzter Tag der Gueltigkeit, "
                                                        "danach vergisst Du ihn automatisch. Heute oder spaeter."},
                "id": {"type": "integer", "description": "id eines vorhandenen Eintrags, der ersetzt werden soll"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_season_plan",
        "description": "Liest den Saisonplan (ATP): je Woche Phase, Wochenziel (TSS/Stunden), Entlastung, Soll/Ist-Last und CTL/TSB "
                       "(Ist bis heute, danach Prognose aus den Wochenzielen), dazu die Events mit Prioritaet und Form am Eventtag. "
                       "Ohne Datum: von vier Wochen zurueck bis 52 Wochen voraus. checks enthaelt Hinweise auf Probleme im Plan.",
        "input_schema": {"type": "object", "properties": {"start": _DATE, "end": _DATE}},
    },
    {
        "name": "set_season_plan_weeks",
        "description": "Legt Wochen des Saisonplans (ATP) an oder aktualisiert sie (hoechstens 80 je Aufruf, teile lange Plaene auf). "
                       "Wochen ohne Eintrag zaehlen in der Prognose als Ruhe, plane also lueckenlos. Das Ergebnis enthaelt die Prognose "
                       "und checks: behebe Hinweise (zu steiler CTL-Anstieg, fehlende Entlastung, Form am Event) und speichere erneut, "
                       "bevor Du antwortest. Legt keine einzelnen Trainings an.",
        "input_schema": {
            "type": "object",
            "properties": {"weeks": {
                "type": "array", "minItems": 1, "maxItems": A.MAX_WEEKS_PER_CALL,
                "items": {
                    "type": "object",
                    "properties": {
                        "week_start": {**_DATE, "description": "Montag der Woche (ein anderer Tag wird auf den Montag der Woche gesetzt)"},
                        "phase": {"type": "string", "enum": list(A.PHASES),
                                  "description": "preparation Vorbereitung, base Grundlage, build Aufbau, peak Spitze, race Wettkampf, transition Uebergang/Offseason"},
                        "tss_target": {"type": "number", "description": "Ziel-TSS der Woche (0-3000)"},
                        "hours_target": {"type": "number", "description": "Optional: Ziel-Stunden der Woche"},
                        "recovery": {"type": "boolean", "description": "true bei Entlastungswoche"},
                        "note": {"type": "string", "description": "Optional: Schwerpunkt der Woche, hoechstens 200 Zeichen"},
                    },
                    "required": ["week_start", "phase", "tss_target"],
                },
            }},
            "required": ["weeks"],
        },
    },
    {
        "name": "clear_season_plan_weeks",
        "description": "Loescht Wochen des Saisonplans im angegebenen Zeitraum (beide Daten sind Pflicht, die Wochen davon sind eingeschlossen). "
                       "Nutze es nur, wenn der Athlet den Plan verwerfen oder neu aufbauen will. Events bleiben bestehen.",
        "input_schema": {"type": "object", "properties": {"start": _DATE, "end": _DATE}, "required": ["start", "end"]},
    },
    {
        "name": "save_season_event",
        "description": "Legt ein Event (Wettkampf oder Ziel) im Saisonplan an oder aendert es (mit id). Prioritaet A = Hauptziel der Saison "
                       "(darauf wird die Form hingearbeitet), B = wichtig, C = Trainingswettkampf ohne Tapering.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "date": _DATE,
                "priority": {"type": "string", "enum": list(A.PRIORITIES)},
                "notes": {"type": "string", "description": "Optional, hoechstens 300 Zeichen (Strecke, Hoehenmeter, Ziel)"},
                "id": {"type": "integer", "description": "id eines vorhandenen Events, das geaendert werden soll"},
            },
            "required": ["name", "date", "priority"],
        },
    },
    {
        "name": "delete_season_event",
        "description": "Loescht ein Event aus dem Saisonplan (Absage, Fehleintrag oder auf Wunsch des Athleten).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "forget_memory",
        "description": "Loescht einen Eintrag aus Deinem Gedaechtnis, wenn er ueberholt oder widerrufen ist oder der Athlet es verlangt.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
]


# ----------------------------------------------------------------- Helfer ---


def _date(v: Any, name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise ToolError(f"{name}: '{v}' ist kein Datum im Format YYYY-MM-DD")


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return min(max(int(v), lo), hi) if v is not None else default
    except (TypeError, ValueError):
        return default


def _workout_view(w, structure: bool = False) -> dict:
    d = {
        "id": w.id, "date": w.date.isoformat(), "title": w.title, "status": w.status,
        "duration_min": round(w.planned_duration_s / 60) if w.planned_duration_s else None,
        "planned_tss": round(w.planned_tss) if w.planned_tss is not None else None,
        "actual_tss": round(w.actual_tss) if getattr(w, "actual_tss", None) is not None else None,
        "created_by": w.created_by,
    }
    if w.description:
        d["description"] = w.description
    if structure:
        d["structure"] = w.structure
    return d


def _week_checks(db: Session, user: User, dates: set[dt.date]) -> list[dict]:
    """Vergleicht die geplante Wochenlast mit der Referenz 7 x CTL und markiert zu grosse Spruenge."""
    rows = pmc_rows(db, user.id)
    ctl = rows[-1]["ctl"] if rows else 0.0
    out = []
    for monday in sorted({d - dt.timedelta(days=d.weekday()) for d in dates}):
        ws, _ = calendar_data(db, user, monday, monday + dt.timedelta(days=6))
        planned = sum((w.planned_tss or 0) for w in ws if w.status != "skipped")
        ref = round(ctl * 7)
        check = {"week_start": monday.isoformat(), "planned_tss": round(planned), "reference_tss_7xCTL": ref,
                 "workouts": len([w for w in ws if w.status != "skipped"])}
        week = db.scalar(select(AtpWeek).where(AtpWeek.user_id == user.id, AtpWeek.week_start == monday))
        if week:  # Wochenziel aus dem Saisonplan (ATP)
            check["atp_target_tss"] = round(week.tss_target)
            check["atp_phase"] = A.PHASES[week.phase]
            if week.tss_target > 0 and planned > week.tss_target * 1.15:
                check["atp_note"] = "Geplante Last liegt mehr als 15 % ueber dem Wochenziel des Saisonplans."
            elif week.tss_target > 0 and planned < week.tss_target * 0.85:
                check["atp_note"] = "Geplante Last liegt mehr als 15 % unter dem Wochenziel des Saisonplans (evtl. noch nicht alle Tage geplant)."
        if ref >= 70:
            ratio = planned / ref
            check["ratio_to_reference"] = round(ratio, 2)
            if ratio > 1.35:
                check["warning"] = "Wochenlast mehr als 35 % ueber Referenz: Gefahr von Ueberlastung, reduzieren."
            elif ratio < 0.5:
                check["note"] = "Wochenlast deutlich unter Referenz (Erholungswoche oder Detraining)."
        else:
            check["note"] = "Kaum Vergleichsbasis (CTL niedrig/keine Daten), Last vorsichtig steigern."
        out.append(check)
    return out


# ---------------------------------------------------------------- Tools ---


def get_athlete_profile(db: Session, user: User, args: dict) -> dict:
    p = user.profile
    return {
        "name": p.name, "ftp_w": p.ftp, "weight_kg": p.weight_kg,
        "w_per_kg": round(p.ftp / p.weight_kg, 2) if p.weight_kg else None,
        "hr_max": p.hr_max, "hr_rest": p.hr_rest, "lthr": p.lthr,
        "goals": p.goals, "availability_min_per_weekday": p.availability,
        "power_zones": power_zones(p.ftp),
    }


def get_fitness_status(db: Session, user: User, args: dict) -> dict:
    weeks = _int(args.get("weeks"), 8, 1, 26)
    rows = pmc_rows(db, user.id)
    return {"current": current_status(rows), "weekly": weekly_summary(db, user.id, weeks)}


def get_recent_activities(db: Session, user: User, args: dict) -> dict:
    days = _int(args.get("days"), 14, 1, 90)
    since = dt.datetime.combine(dt.date.today() - dt.timedelta(days=days - 1), dt.time.min)
    acts = db.scalars(
        select(Activity).where(Activity.user_id == user.id, Activity.start_time >= since)
        .order_by(Activity.start_time.desc()).limit(60)
    )
    return {"activities": [
        {"date": a.start_time.date().isoformat(), "name": a.name, "duration_min": round(a.duration_s / 60),
         "distance_km": round(a.distance_m / 1000, 1), "elevation_m": round(a.elevation_m) if a.elevation_m else None,
         "avg_power_w": round(a.avg_power) if a.avg_power else None, "np_w": round(a.norm_power) if a.norm_power else None,
         "if": round(a.intensity_factor, 2) if a.intensity_factor else None,
         "tss": round(a.tss) if a.tss is not None else None, "avg_hr": round(a.avg_hr) if a.avg_hr else None}
        for a in acts
    ]}


def get_calendar(db: Session, user: User, args: dict) -> dict:
    start, end = _date(args.get("start"), "start"), _date(args.get("end"), "end")
    if end < start or (end - start).days > 100:
        raise ToolError("Zeitraum ungueltig (end >= start, max. 100 Tage)")
    ws, _ = calendar_data(db, user, start, end)
    return {"workouts": [_workout_view(w, bool(args.get("include_structure"))) for w in ws]}


def create_workouts(db: Session, user: User, args: dict) -> dict:
    items = args.get("workouts")
    if not isinstance(items, list) or not items:
        raise ToolError("workouts muss eine nichtleere Liste sein")
    if len(items) > MAX_CREATE:
        raise ToolError(f"Hoechstens {MAX_CREATE} Trainings pro Aufruf")
    today = dt.date.today()
    parsed: list[WorkoutIn] = []
    for i, item in enumerate(items):
        try:
            w = WorkoutIn.model_validate(item)
        except ValidationError as e:
            msgs = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:4])
            raise ToolError(f"Training {i + 1} ungueltig: {msgs}")
        if w.date < today:
            raise ToolError(f"Training {i + 1}: {w.date} liegt in der Vergangenheit")
        if (w.date - today).days > MAX_HORIZON_DAYS:
            raise ToolError(f"Training {i + 1}: maximal {MAX_HORIZON_DAYS} Tage im Voraus planbar")
        w.status = "planned"
        parsed.append(w)
    created = []
    for body in parsed:  # erst nach erfolgreicher Validierung aller Eintraege schreiben
        row = PlannedWorkout(user_id=user.id, created_by="coach")
        _apply(row, body, user.profile.ftp)
        db.add(row)
        created.append(row)
    db.commit()
    return {
        "created": [{"id": r.id, "date": r.date.isoformat(), "title": r.title,
                     "duration_min": round((r.planned_duration_s or 0) / 60), "planned_tss": round(r.planned_tss or 0)}
                    for r in created],
        "week_checks": _week_checks(db, user, {r.date for r in created}),
    }


def _own_future_workout(db: Session, user: User, workout_id: Any) -> PlannedWorkout:
    w = db.get(PlannedWorkout, workout_id) if isinstance(workout_id, int) else None
    if w is None or w.user_id != user.id:
        raise ToolError(f"Training {workout_id} nicht gefunden")
    if w.date < dt.date.today():
        raise ToolError("Vergangene Trainings koennen nicht mehr geaendert werden")
    return w


def update_workout(db: Session, user: User, args: dict) -> dict:
    w = _own_future_workout(db, user, args.get("id"))
    data = {
        "date": w.date.isoformat(), "title": w.title, "description": w.description, "structure": w.structure,
        "planned_duration_s": w.planned_duration_s if not w.structure else None,
        "planned_tss": w.planned_tss if not w.structure else None, "status": w.status,
    }
    data.update({k: v for k, v in args.items() if k in ("date", "title", "description", "structure", "status")})
    try:
        body = WorkoutIn.model_validate(data)
    except ValidationError as e:
        raise ToolError("Aenderung ungueltig: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:4]))
    if body.date < dt.date.today() or (body.date - dt.date.today()).days > MAX_HORIZON_DAYS:
        raise ToolError("Neues Datum ausserhalb des erlaubten Bereichs (heute bis +120 Tage)")
    _apply(w, body, user.profile.ftp)
    db.commit()
    return {"updated": {"id": w.id, "date": w.date.isoformat(), "title": w.title,
                        "duration_min": round((w.planned_duration_s or 0) / 60), "planned_tss": round(w.planned_tss or 0)},
            "week_checks": _week_checks(db, user, {w.date})}


def delete_workout(db: Session, user: User, args: dict) -> dict:
    w = _own_future_workout(db, user, args.get("id"))
    info = {"id": w.id, "date": w.date.isoformat(), "title": w.title}
    db.delete(w)
    db.commit()
    return {"deleted": info}


def update_athlete_notes(db: Session, user: User, args: dict) -> dict:
    p = user.profile
    changed = []
    if "goals" in args:
        goals = str(args["goals"] or "").strip()
        if len(goals) > 2000:
            raise ToolError("goals ist laenger als 2000 Zeichen")
        p.goals = goals or None
        changed.append("goals")
    if "availability" in args:
        av = args["availability"]
        if not isinstance(av, dict):
            raise ToolError("availability muss ein Objekt sein")
        clean = {}
        for k, v in av.items():
            if k not in WEEKDAYS:
                raise ToolError(f"Unbekannter Wochentag '{k}' (erlaubt: {', '.join(WEEKDAYS)})")
            if not isinstance(v, int) or not 0 <= v <= 600:
                raise ToolError(f"{k}: Minuten muessen eine ganze Zahl von 0 bis 600 sein")
            clean[k] = v
        p.availability = clean
        changed.append("availability")
    if not changed:
        raise ToolError("Nichts zu speichern: goals und/oder availability angeben")
    db.commit()
    return {"saved": changed}


def active_memories(db: Session, user_id: int, today: dt.date | None = None) -> list[CoachMemory]:
    """Gueltige Eintraege (abgelaufene werden ignoriert), aelteste zuerst."""
    today = today or dt.date.today()
    return list(db.scalars(
        select(CoachMemory).where(
            CoachMemory.user_id == user_id,
            (CoachMemory.valid_until.is_(None)) | (CoachMemory.valid_until >= today),
        ).order_by(CoachMemory.id)
    ))


def memory_line(m: CoachMemory) -> str:
    until = f" (gilt bis {m.valid_until.isoformat()})" if m.valid_until else ""
    return f"[{m.id}] {m.text}{until}"


def save_memory(db: Session, user: User, args: dict) -> dict:
    text = " ".join(str(args.get("text") or "").split())
    if not text:
        raise ToolError("text darf nicht leer sein")
    if len(text) > MAX_MEMORY_CHARS:
        raise ToolError(f"text ist laenger als {MAX_MEMORY_CHARS} Zeichen, fasse Dich kuerzer")
    until = None
    if args.get("valid_until"):
        until = _date(args["valid_until"], "valid_until")
        if until < dt.date.today():
            raise ToolError("valid_until liegt in der Vergangenheit")
    mem = None
    if args.get("id") is not None:
        mem = db.get(CoachMemory, args["id"]) if isinstance(args["id"], int) else None
        if mem is None or mem.user_id != user.id:
            raise ToolError("Eintrag nicht gefunden")
    current = active_memories(db, user.id)
    if mem is None:
        same = next((m for m in current if m.text.casefold() == text.casefold()), None)
        if same is not None:  # schon vorhanden: nichts doppelt speichern, nur Gueltigkeit nachziehen
            if until and same.valid_until != until:
                same.valid_until = until
                db.commit()
            return {"saved": memory_line(same), "note": "Eintrag existierte bereits"}
        if len(current) >= MAX_MEMORIES:
            raise ToolError(f"Gedaechtnis ist voll ({MAX_MEMORIES} Eintraege). Fasse Eintraege zusammen "
                            "(save_memory mit id) oder loesche Ueberholtes (forget_memory).")
        mem = CoachMemory(user_id=user.id, text=text, valid_until=until)
        db.add(mem)
    else:
        mem.text, mem.valid_until = text, until
    db.commit()
    return {"saved": memory_line(mem)}


def forget_memory(db: Session, user: User, args: dict) -> dict:
    mem = db.get(CoachMemory, args["id"]) if isinstance(args.get("id"), int) else None
    if mem is None or mem.user_id != user.id:
        raise ToolError("Eintrag nicht gefunden")
    text = mem.text
    db.delete(mem)
    db.commit()
    return {"forgotten": text}


def _atp_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except A.AtpError as e:
        raise ToolError(str(e))


def get_season_plan(db: Session, user: User, args: dict) -> dict:
    today = dt.date.today()
    start = _date(args["start"], "start") if args.get("start") else A.monday_of(today) - dt.timedelta(weeks=4)
    end = _date(args["end"], "end") if args.get("end") else A.monday_of(today) + dt.timedelta(weeks=52)
    if end < start or (end - start).days > 110 * 7:
        raise ToolError("end muss nach start liegen, hoechstens 110 Wochen")
    plan = A.get_plan(db, user.id, start, end, today)
    weeks = [w for w in plan["weeks"] if w["phase"] or w["actual_tss"] or w["planned_tss"]]  # leere Wochen sparen Platz
    return {"weeks": weeks, "events": plan["events"], "checks": A.plan_checks(plan, today)}


def set_season_plan_weeks(db: Session, user: User, args: dict) -> dict:
    starts = _atp_call(A.upsert_weeks, db, user.id, args.get("weeks"))
    plan = A.full_plan(db, user.id)
    saved = {d.isoformat() for d in starts}
    return {
        "saved_weeks": len(starts), "first_week": starts[0].isoformat(), "last_week": starts[-1].isoformat(),
        "projection": [{"week_start": w["week_start"], "phase": w["phase"], "tss_target": w["tss_target"], "ctl": w["ctl"], "tsb": w["tsb"]}
                       for w in plan["weeks"] if w["week_start"] in saved],
        "events": plan["events"],
        "checks": A.plan_checks(plan),
    }


def clear_season_plan_weeks(db: Session, user: User, args: dict) -> dict:
    if not args.get("start") or not args.get("end"):
        raise ToolError("start und end sind Pflicht")
    n = A.clear_weeks(db, user.id, _date(args["start"], "start"), _date(args["end"], "end"))
    return {"deleted_weeks": n}


def save_season_event(db: Session, user: User, args: dict) -> dict:
    ev = _atp_call(A.save_event, db, user.id, args)
    return {"saved": {"id": ev.id, "name": ev.name, "date": ev.date.isoformat(), "priority": ev.priority}}


def delete_season_event(db: Session, user: User, args: dict) -> dict:
    return {"deleted": _atp_call(A.delete_event, db, user.id, args.get("id"))}


HANDLERS = {
    "get_athlete_profile": get_athlete_profile,
    "get_fitness_status": get_fitness_status,
    "get_recent_activities": get_recent_activities,
    "get_calendar": get_calendar,
    "create_workouts": create_workouts,
    "update_workout": update_workout,
    "delete_workout": delete_workout,
    "update_athlete_notes": update_athlete_notes,
    "save_memory": save_memory,
    "forget_memory": forget_memory,
    "get_season_plan": get_season_plan,
    "set_season_plan_weeks": set_season_plan_weeks,
    "clear_season_plan_weeks": clear_season_plan_weeks,
    "save_season_event": save_season_event,
    "delete_season_event": delete_season_event,
}

# Tools, die etwas veraendern (fuer die Aktionsliste in der App)
WRITE_TOOLS = {"create_workouts", "update_workout", "delete_workout", "update_athlete_notes", "save_memory", "forget_memory",
               "set_season_plan_weeks", "clear_season_plan_weeks", "save_season_event", "delete_season_event"}


def action_summary(name: str, args: dict, result: dict) -> str:
    if name == "create_workouts":
        return f"{len(result['created'])} Training(s) angelegt"
    if name == "update_workout":
        return f"Training geaendert: {result['updated']['title']} ({result['updated']['date']})"
    if name == "delete_workout":
        return f"Training geloescht: {result['deleted']['title']} ({result['deleted']['date']})"
    if name == "set_season_plan_weeks":
        return f"Saisonplan: {result['saved_weeks']} Woche(n) gespeichert"
    if name == "clear_season_plan_weeks":
        return f"Saisonplan: {result['deleted_weeks']} Woche(n) geloescht"
    if name == "save_season_event":
        return f"Event gespeichert: {result['saved']['name']} ({result['saved']['date']})"[:120]
    if name == "delete_season_event":
        return f"Event geloescht: {result['deleted']}"[:120]
    if name == "save_memory":
        return f"Gemerkt: {args.get('text', '')}"[:120]
    if name == "forget_memory":
        return f"Vergessen: {result['forgotten']}"[:120]
    return "Ziele/Verfuegbarkeit gespeichert"
