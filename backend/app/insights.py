"""Analyse von Training und Rennen mit Datenbankzugriff: Kennzahlen je Fahrt, Soll/Ist, Belastung, FTP und das
Feedback des Coaches zu jeder Fahrt.

Die Berechnungen stecken in app/metrics/analysis.py (reine Funktionen). Hier werden Daten geladen, Sensordaten
bei Strava nachgeladen, Ergebnisse in ActivityInsight gespeichert und das Feedback per Modell erzeugt.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

import anthropic
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import atp as A
from .config import get_settings
from .db import SessionLocal
from .integrations import strava
from .metrics import analysis as AN
from .metrics.fitness import pmc_rows
from .metrics.power import POWER_ZONES
from .models import Activity, ActivityInsight, AtpWeek, Integration, PlannedWorkout, SeasonEvent, User
from .routers.plans import calendar_data

log = logging.getLogger(__name__)

AUTO_FEEDBACK_DAYS = 3  # automatisches Feedback nur fuer frische Fahrten (nicht beim Import der ganzen Historie)
AUTO_FEEDBACK_MAX = 5
FEEDBACK_MAX_TOKENS = 6000
BACKFILL_DEFAULT = 6


class InsightError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------ Grundlagen ---


def insight_row(db: Session, act: Activity, create: bool = True) -> ActivityInsight | None:
    row = db.scalar(select(ActivityInsight).where(ActivityInsight.activity_id == act.id))
    if row is None and create:
        row = ActivityInsight(activity_id=act.id, user_id=act.user_id)
        db.add(row)
        db.flush()
    return row


def set_workout_type(db: Session, act: Activity, workout_type: Any) -> None:
    """Merkt sich die Strava-Markierung (11 = Rennen). Wird beim Import aufgerufen."""
    if workout_type is None:
        return
    try:
        wt = int(workout_type)
    except (TypeError, ValueError):
        return
    if act.id is None:
        db.flush()
    row = insight_row(db, act)
    row.workout_type = wt


def delete_for(db: Session, act: Activity) -> None:
    row = insight_row(db, act, create=False)
    if row is not None:
        db.delete(row)


def ensure_streams(db: Session, user: User, act: Activity) -> bool:
    """Holt fehlende Sensordaten bei Strava (1 Anfrage). False, wenn es keine gibt oder Strava nicht erreichbar ist."""
    if act.streams:
        return True
    if act.source != "strava":
        return False
    integ = db.scalar(select(Integration).where(Integration.user_id == user.id, Integration.provider == "strava"))
    if integ is None:
        return False
    streams = strava.StravaClient(db, integ).get_streams(act.external_id)  # StravaError geht an den Aufrufer
    strava.apply_streams(act, streams, user.profile)
    db.commit()
    return bool(act.streams)


def _series(act: Activity) -> tuple[list[float], list[float], list[float]]:
    s = act.streams or {}
    t = s.get("time") or []
    def one(key: str) -> list[float]:
        v = s.get(key)
        return strava.resample_1hz(t, v) if v and t else []
    return one("watts"), one("heartrate"), one("cadence")


def metrics_for(db: Session, user: User, act: Activity, *, fetch: bool = True) -> dict | None:
    """Kennzahlen aus den Sensordaten (gespeichert; neu berechnet bei geaenderter FTP oder Berechnung)."""
    row = insight_row(db, act)
    ftp = user.profile.ftp
    m = row.metrics
    if m and m.get("version") == AN.METRICS_VERSION and m.get("ftp_used") == ftp:
        return m
    if not act.streams:
        if not fetch:
            return None
        try:
            if not ensure_streams(db, user, act):
                return None
        except strava.StravaError as e:
            log.info("Sensordaten fuer Aktivitaet %s nicht geladen: %s", act.id, e)
            return None
    watts, hr, cad = _series(act)
    row.metrics = AN.ride_metrics(watts, hr, ftp, cadence=cad, duration_s=act.duration_s)
    db.commit()
    return row.metrics


def planned_workout_for(db: Session, user: User, act: Activity) -> PlannedWorkout | None:
    """Das geplante Training, dem der Kalender diese Aktivitaet zuordnet."""
    day = act.start_time.date()
    workouts, _ = calendar_data(db, user, day, day)
    hit = next((w for w in workouts if w.activity_id == act.id), None)
    return db.get(PlannedWorkout, hit.id) if hit else None


def _event_on(db: Session, user: User, day: dt.date) -> SeasonEvent | None:
    return db.scalar(select(SeasonEvent).where(SeasonEvent.user_id == user.id, SeasonEvent.date == day))


def race_flag(db: Session, user: User, act: Activity) -> bool:
    row = insight_row(db, act, create=False)
    return AN.is_race(act.name, row.workout_type if row else None, _event_on(db, user, act.start_time.date()) is not None,
                      act.intensity_factor)


def _form_before(db: Session, user: User, day: dt.date) -> dict | None:
    rows = pmc_rows(db, user.id, day)
    row = next((r for r in rows if r["date"] == day), None)
    if row is None:
        return None
    # TSB ist die Form am Morgen (vor der Fahrt), CTL/ATL gelten nach dem Tag
    return {"tsb_morning": round(row["tsb"], 1), "ctl_after": round(row["ctl"], 1), "atl_after": round(row["atl"], 1),
            "tss_day": round(row["tss"])}


def _history_mmp(db: Session, user: User, act: Activity) -> list[dict]:
    t1 = act.start_time
    t0 = t1 - dt.timedelta(days=90)
    acts = list(db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.start_time >= t0, Activity.start_time < t1)))
    mm = _metrics_map(db, user, acts)
    return [{"mmp": m.get("mmp") or {}} for m in mm.values()]


def _compact(m: dict) -> dict:
    """Kennzahlen fuer Modell und App: Zonen in Minuten, Bestwerte mit Beschriftung, nur die wichtigsten Belastungen."""
    out = {k: m[k] for k in ("avg_power", "np", "intensity", "vi", "time_above_ftp_s", "coasting_pct", "matches",
                             "decoupling_pct", "ef", "cadence_avg", "pacing", "hr", "effort_count") if m.get(k) is not None}
    if m.get("zones_s"):
        total = sum(m["zones_s"]) or 1
        out["zones"] = [{"zone": f"Z{i + 1}", "name": POWER_ZONES[i][0].split(" ", 1)[1], "min": round(s / 60),
                         "pct": round(s / total * 100)} for i, s in enumerate(m["zones_s"])]
    if m.get("mmp"):
        out["best_powers"] = {AN.MMP_LABELS[int(k)]: v for k, v in m["mmp"].items() if int(k) in AN.MMP_LABELS}
    if m.get("efforts"):
        out["efforts"] = [{"start_min": round(e["start_s"] / 60, 1), "duration_s": e["duration_s"], "avg_w": e["avg_w"],
                           "pct_ftp": e["pct_ftp"]} for e in m["efforts"][:12]]
    return out


def activity_report(db: Session, user: User, act: Activity, *, fetch: bool = True) -> dict:
    """Alles, was der Coach und die App fuer die Analyse einer Fahrt brauchen."""
    ftp = user.profile.ftp
    m = metrics_for(db, user, act, fetch=fetch)
    race = race_flag(db, user, act)
    event = _event_on(db, user, act.start_time.date())
    kind = AN.classify(m.get("zones_s") or [], m.get("intensity"), m.get("efforts") or [], race, m.get("matches") or 0) if m and m.get("zones_s") else (
        "race" if race else "recovery" if (act.intensity_factor or 1) < 0.62 else "endurance" if act.intensity_factor else None)
    report: dict = {
        "activity": {
            "id": act.id, "date": act.start_time.date().isoformat(), "start": act.start_time.strftime("%H:%M"), "name": act.name,
            "duration_min": round(act.duration_s / 60), "distance_km": round(act.distance_m / 1000, 1),
            "elevation_m": round(act.elevation_m) if act.elevation_m else None,
            "avg_power_w": round(act.avg_power) if act.avg_power else None, "np_w": round(act.norm_power) if act.norm_power else None,
            "if": round(act.intensity_factor, 2) if act.intensity_factor else None,
            "tss": round(act.tss) if act.tss is not None else None, "avg_hr": round(act.avg_hr) if act.avg_hr else None,
        },
        "ftp_w": round(ftp),
        "type": kind, "type_label": AN.RIDE_TYPES.get(kind or "", "Unbekannt"), "race": race,
    }
    if event:
        report["event"] = {"name": event.name, "priority": event.priority}
    quality = []
    if m is None:
        quality.append("Keine Sensordaten verfuegbar: nur Zusammenfassung von Strava.")
    elif not m.get("np"):
        quality.append("Keine Leistungsdaten (kein Powermeter): Intensitaet und TSS sind aus dem Puls geschaetzt oder fehlen.")
    if act.tss is not None and not act.avg_power:
        quality.append("TSS ist aus dem Puls geschaetzt.")
    if quality:
        report["data_quality"] = quality
    if m:
        report["metrics"] = _compact(m)
        pbs = AN.personal_bests(m.get("mmp") or {}, _history_mmp(db, user, act))
        if pbs:
            report["personal_bests_90d"] = pbs
    plan = planned_workout_for(db, user, act)
    if plan:
        report["plan"] = {"title": plan.title, "description": (plan.description or "")[:600] or None,
                          "planned_tss": round(plan.planned_tss) if plan.planned_tss is not None else None,
                          "planned_min": round(plan.planned_duration_s / 60) if plan.planned_duration_s else None,
                          "structured": bool(plan.structure)}
        watts = _series(act)[0] if act.streams else []
        comp = AN.plan_compliance(plan.structure, ftp, watts, planned_tss=plan.planned_tss, actual_tss=act.tss,
                                  planned_duration_s=plan.planned_duration_s, actual_duration_s=act.duration_s)
        if comp:
            report["compliance"] = comp
    form = _form_before(db, user, act.start_time.date())
    if form:
        report["form_before"] = form
    week = db.scalar(select(AtpWeek).where(AtpWeek.user_id == user.id,
                                           AtpWeek.week_start == A.monday_of(act.start_time.date())))
    if week:
        report["season_plan_week"] = {"phase": A.PHASES.get(week.phase, week.phase), "tss_target": round(week.tss_target),
                                      "recovery_week": week.recovery}
    return report


# ------------------------------------------------------- Belastung und FTP ---


def _acts_since(db: Session, user: User, since: dt.date) -> list[Activity]:
    return list(db.scalars(select(Activity).where(
        Activity.user_id == user.id, Activity.start_time >= dt.datetime.combine(since, dt.time.min)).order_by(Activity.start_time)))


def _metrics_map(db: Session, user: User, acts: list[Activity]) -> dict[int, dict]:
    """Kennzahlen je Fahrt; vorhandene Sensordaten werden bei Bedarf ausgewertet, nichts wird bei Strava nachgeladen."""
    out: dict[int, dict] = {}
    for a in acts:
        if a.streams:
            m = metrics_for(db, user, a, fetch=False)
        else:
            row = insight_row(db, a, create=False)
            m = row.metrics if row else None
        if m:
            out[a.id] = m
    return out


def intensity_distribution(db: Session, user: User, today: dt.date, days: int = 28) -> dict | None:
    """Zeitanteile nach Leistungszonen der letzten Wochen (nur Fahrten mit ausgewerteten Sensordaten)."""
    acts = _acts_since(db, user, today - dt.timedelta(days=days - 1))
    mm = _metrics_map(db, user, acts)
    zs = [0] * 7
    rides = 0
    for a in acts:
        z = (mm.get(a.id) or {}).get("zones_s")
        if z:
            rides += 1
            zs = [x + y for x, y in zip(zs, z)]
    total = sum(zs)
    if not total:
        return None
    pct = lambda s: round(s / total * 100)  # noqa: E731
    return {"rides_with_data": rides, "rides_total": len(acts), "hours": round(total / 3600, 1),
            "low_z1_z2_pct": pct(zs[0] + zs[1]), "tempo_z3_pct": pct(zs[2]), "threshold_z4_pct": pct(zs[3]),
            "high_z5plus_pct": pct(zs[4] + zs[5] + zs[6])}


def load_report(db: Session, user: User, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    rows = pmc_rows(db, user.id, today)
    start = today - dt.timedelta(days=13)
    workouts, acts = calendar_data(db, user, start, today)
    planned = sum((w.planned_tss or 0) for w in workouts if w.status != "skipped")
    actual = sum((a.tss or 0) for a in acts)
    this_monday = A.monday_of(today)
    last_monday = this_monday - dt.timedelta(days=7)
    atp_last = db.scalar(select(AtpWeek).where(AtpWeek.user_id == user.id, AtpWeek.week_start == last_monday))
    atp_now = db.scalar(select(AtpWeek).where(AtpWeek.user_id == user.id, AtpWeek.week_start == this_monday))
    last_week_actual = sum((a.tss or 0) for a in _acts_since(db, user, last_monday) if a.start_time.date() < this_monday)
    nxt = db.scalar(select(SeasonEvent).where(SeasonEvent.user_id == user.id, SeasonEvent.date >= today).order_by(SeasonEvent.date))
    recent = _acts_since(db, user, today - dt.timedelta(days=56))
    mm = _metrics_map(db, user, recent)
    ef_rides = [{"date": a.start_time.date(), "ef": mm[a.id].get("ef")} for a in recent
                if a.id in mm and mm[a.id].get("ef") and (mm[a.id].get("intensity") or 1) < 0.8 and a.duration_s >= 2700]
    res = AN.load_assessment(
        rows, today=today, planned_14d=planned, actual_14d=actual,
        atp_last_week={"target": atp_last.tss_target, "actual": last_week_actual, "recovery": atp_last.recovery} if atp_last else None,
        atp_phase_now=atp_now.phase if atp_now else None,
        event_within_days=(nxt.date - today).days if nxt else None, ef_trend_pct=AN.ef_trend(ef_rides, today),
    )
    res["context"] = {
        "planned_tss_14d": round(planned), "actual_tss_14d": round(actual),
        "season_phase": A.PHASES.get(atp_now.phase) if atp_now else None,
        "week_target_tss": round(atp_now.tss_target) if atp_now else None,
        "next_event": {"name": nxt.name, "date": nxt.date.isoformat(), "priority": nxt.priority, "in_days": (nxt.date - today).days} if nxt else None,
    }
    dist = intensity_distribution(db, user, today)
    if dist:
        res["intensity_distribution_28d"] = dist
    return res


def backfill_streams(db: Session, user: User, limit: int = BACKFILL_DEFAULT, today: dt.date | None = None) -> int:
    """Laedt Sensordaten der intensivsten Fahrten der letzten 90 Tage nach (schont das Strava-Limit)."""
    today = today or dt.date.today()
    acts = [a for a in _acts_since(db, user, today - dt.timedelta(days=89))
            if not a.streams and a.source == "strava" and a.norm_power and a.duration_s >= 600]
    acts.sort(key=lambda a: -(a.norm_power or 0) * min(a.duration_s, 3600))
    n = 0
    for a in acts[:limit]:
        try:
            if ensure_streams(db, user, a):
                metrics_for(db, user, a, fetch=False)
                n += 1
        except strava.StravaError as e:
            log.info("Nachladen abgebrochen: %s", e)
            break
    return n


def ftp_report(db: Session, user: User, today: dt.date | None = None, *, backfill: int = 0) -> dict:
    today = today or dt.date.today()
    loaded = backfill_streams(db, user, backfill, today) if backfill else 0
    acts = [a for a in _acts_since(db, user, today - dt.timedelta(days=89)) if a.avg_power]
    rides = []
    for a in acts:
        m = metrics_for(db, user, a, fetch=False) if a.streams else None
        rides.append({"date": a.start_time.date(), "name": a.name, "duration_s": a.duration_s, "np": a.norm_power,
                      "mmp": (m or {}).get("mmp")})
    ctl_by_date = {r["date"]: r["ctl"] for r in pmc_rows(db, user.id, today) if (today - r["date"]).days <= 90}
    res = AN.ftp_assessment(user.profile.ftp, rides, today, ctl_by_date)
    res["rides_with_power_90d"] = len(rides)
    res["rides_with_sensor_data_90d"] = sum(1 for r in rides if r["mmp"])
    if loaded:
        res["streams_loaded_now"] = loaded
    if user.profile.weight_kg:
        res["w_per_kg"] = round(user.profile.ftp / user.profile.weight_kg, 2)
    return res


def recompute_tss(db: Session, user: User) -> int:
    """TSS aller Fahrten mit der aktuellen FTP neu berechnen (wie POST /metrics/recompute)."""
    from .metrics.power import intensity_factor, tss

    ftp = user.profile.ftp
    n = 0
    for a in db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.norm_power.is_not(None))):
        a.intensity_factor = intensity_factor(a.norm_power, ftp)
        a.tss = tss(a.duration_s, a.norm_power, ftp)
        a.ftp_used = ftp
        n += 1
    db.commit()
    return n


# ---------------------------------------------------------------- Feedback ---

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "Kernaussage in hoechstens 70 Zeichen"},
        "summary": {"type": "string", "description": "2-4 Saetze: Was war das, wie lief es, passt es zum Ziel und zur Form?"},
        "execution": {"type": "string", "enum": ["as_planned", "harder", "easier", "partial", "unplanned", "race"]},
        "load_fit": {"type": "string", "enum": ["fits", "too_much", "too_little", "unclear"],
                     "description": "Passt die Belastung dieser Fahrt zum aktuellen Zustand und zur Phase?"},
        "positives": {"type": "array", "items": {"type": "string"}, "description": "0-3 kurze Punkte"},
        "improvements": {"type": "array", "items": {"type": "string"}, "description": "0-3 kurze, umsetzbare Punkte"},
        "next": {"type": "string", "description": "Ein Satz: Erholung oder naechster Schritt"},
        "ftp_hint": {"type": "string", "description": "Leer, ausser die Fahrt deutet auf eine zu niedrige oder zu hohe FTP hin"},
    },
    "required": ["headline", "summary", "execution", "load_fit", "positives", "improvements", "next", "ftp_hint"],
    "additionalProperties": False,
}

FEEDBACK_PROMPT = """Du bist der persoenliche Radtrainer des Athleten und schreibst das Feedback zu einer absolvierten Fahrt. \
Deutsch, per Du (Du, Dein, Dich gross), direkt, konkret und motivierend, ohne Floskeln. Kein Markdown.

Grundlage sind ausschliesslich die Daten unten (Analyse der Fahrt, Plan, Form, Belastungsbewertung, FTP-Pruefung, Gedaechtnis). \
Erfinde keine Zahlen; nenne konkrete Werte (Watt, % FTP, Minuten, TSS), wenn sie die Aussage tragen.

So gehst Du vor:
- Einordnen: Art der Fahrt (Grundlage, Intervalle, Rennen ...), Ziel laut Plan und Saisonphase.
- Mit Plan: Soll und Ist vergleichen (TSS, Dauer, Intervalle getroffen, zu hart, zu locker, Leistungsabfall ueber die Serie). \
Zu hart gefahrene Grundlage oder Erholung ist ein Fehler, zu niedrige Intervalle sind es auch. Nenne die Ursache, wenn die Daten sie zeigen.
- Ohne Plan: Wofuer war die Fahrt gut, passte sie in die Woche?
- Rennen: Verlauf (Pacing erstes gegen letztes Drittel, Spitzen, Zeit ueber FTP, Bestwerte), Form (TSB) am Renntag im Vergleich zum Ziel, \
und wie viele Tage locker danach sinnvoll sind.
- Belastung: Passt die Fahrt zum aktuellen Zustand (TSB, Ermuedung, Belastungsbewertung, Phase, Gedaechtnis z. B. Offseason)? \
Sag deutlich, wenn es zu viel oder zu wenig war.
- Vorrang hat, was Du ueber den Athleten weisst: Gedaechtnis, bisheriges Gespraech, Ziele, Saisonplan und die Einordnung des Coaches \
(sie beruecksichtigt das alles schon). Die automatische Belastungsbewertung ist nur eine Rechnung aus Zahlen und kennt keine Absprachen. \
Gilt eine bewusste Pause, Offseason, ein Uebergang, Tapering, Krankheit oder Verletzung, dann sind niedrige Last, sinkende Fitness und \
hohe Form gewollt: load_fit ist dann fits, und Du empfiehlst nie mehr Umfang oder mehr Training, als vereinbart ist \
(z. B. nichts vor dem vereinbarten Trainingsstart). Bei Offseason eher: locker weiterfahren, Erholung geniessen, Termin des Starts nennen. \
Widersprich nie dem Gedaechtnis oder dem Gespraech.
- Ausdauer: Entkopplung (Pw:HR) unter 5 % spricht bei langen gleichmaessigen Fahrten fuer gute Grundlage, ueber 8-10 % fuer Ermuedung, \
Hitze, zu wenig Essen oder zu hohes Tempo (Praxisregel). Nur erwaehnen, wenn vorhanden und relevant.
- FTP: Deuten Fahrt oder FTP-Pruefung auf eine zu niedrige FTP (z. B. 20 min ueber 105 % FTP, NP einer langen Fahrt ueber FTP), \
schreib es in ftp_hint mit dem Vorschlag aus der FTP-Pruefung; der Athlet kann ihn in der App uebernehmen. Sonst ftp_hint leer.
- Bestwerte: best_powers sind die besten Werte dieser Fahrt, keine Rekorde. Neue Bestleistungen gegenueber den 90 Tagen davor \
stehen nur in personal_bests_90d; die kurz wuerdigen.
- Erfinde keine Empfindungen (Gefuehl, Beine, Motivation), Wetter oder Umstaende, die nicht in den Daten stehen.
- Datenqualitaet: Ohne Powermeter nur vorsichtig urteilen und das sagen.
- Gesundheit: Bei Hinweisen auf Ueberlastung oder Krankheit (Puls auffaellig, Abbruch) zur Pause raten; keine Diagnosen.
Schwellen wie TSB-Bereiche und Entkopplung sind Praxisregeln, keine Studienergebnisse."""


def _feedback_today(db: Session, user: User) -> int:
    midnight = dt.datetime.combine(dt.date.today(), dt.time.min, tzinfo=dt.timezone.utc)
    return db.scalar(select(func.count()).select_from(ActivityInsight).where(
        ActivityInsight.user_id == user.id, ActivityInsight.feedback_status == "done", ActivityInsight.updated_at >= midnight)) or 0


def generate_feedback(db: Session, user: User, act: Activity, *, client: Any = None, force: bool = False) -> dict:
    """Erzeugt (oder liefert gespeichertes) Feedback zu einer Fahrt."""
    from .coach.agent import _client, _stream, build_context  # spaet importiert: agent importiert die Werkzeuge

    settings = get_settings()
    row = insight_row(db, act)
    if row.feedback and not force:
        return row.feedback
    if client is None and not settings.anthropic_api_key:
        raise InsightError("Der Coach ist nicht eingerichtet: ANTHROPIC_API_KEY fehlt in backend/.env", 503)
    if _feedback_today(db, user) >= settings.coach_feedback_daily_limit:
        raise InsightError("Tageslimit fuer Trainings-Feedback erreicht", 429)
    report = activity_report(db, user, act)
    day = act.start_time.date()
    load = load_report(db, user, day)
    ftp = ftp_report(db, user)  # Stand heute: der Hinweis soll zur aktuellen Empfehlung in der App passen
    from .coach.form_hint import _chat_lines  # spaet importiert wie oben

    chat, _ = _chat_lines(db, user)
    # Einordnung des Coaches (Gedaechtnis und Gespraech eingerechnet) fuer Fahrten der letzten Tage; bei aelteren Fahrten
    # waere der heutige Stand irrefuehrend, dort gilt die reine Rechnung zusammen mit dem Gedaechtnis im Kontext
    view = coach_load_view(db, user, load, client=client) if (dt.date.today() - day).days <= AUTO_FEEDBACK_DAYS + 2 else None
    prompt = "\n".join([
        build_context(db, user, day), "",
        "Letzter Teil des Gespraechs (aelteste zuerst):", *(chat or ["(noch kein Gespraech)"]), "",
        "Analyse der Fahrt (JSON):", json.dumps(report, ensure_ascii=False), "",
        "Automatische Belastungsbewertung, nur Zahlen ohne Kenntnis von Absprachen (JSON):",
        json.dumps({k: load[k] for k in ("verdict", "flags", "metrics", "context")}, ensure_ascii=False), "",
        *(["Einordnung des Coaches mit Gedaechtnis und Gespraech (hat Vorrang):", json.dumps(view, ensure_ascii=False), ""] if view else []),
        "FTP-Pruefung (JSON):", json.dumps({k: ftp.get(k) for k in ("ftp", "recommendation", "suggested_ftp", "confidence", "reason")}, ensure_ascii=False), "",
        "Schreibe jetzt das Feedback zu dieser Fahrt.",
    ])
    model = settings.coach_chat_model
    try:
        final = _stream(client or _client(settings), dict(
            model=model, max_tokens=FEEDBACK_MAX_TOKENS, system=FEEDBACK_PROMPT,
            messages=[{"role": "user", "content": prompt}], thinking={"type": "adaptive"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": FEEDBACK_SCHEMA}},
        ), False)
    except anthropic.APIError as e:
        log.warning("Feedback fuer Aktivitaet %s fehlgeschlagen: %s", act.id, e)
        row.feedback_status = "failed"
        db.commit()
        raise InsightError("Der Coach ist gerade nicht erreichbar, bitte spaeter erneut versuchen.", 502)
    text = "".join(b.text for b in final.content if b.type == "text").strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or not data.get("summary"):
            raise ValueError("leer")
    except ValueError:
        log.warning("Feedback fuer Aktivitaet %s nicht lesbar (stop=%s)", act.id, final.stop_reason)
        row.feedback_status = "failed"
        db.commit()
        raise InsightError("Das Feedback konnte nicht erstellt werden, bitte erneut versuchen.", 502)
    fb = {k: data.get(k) for k in FEEDBACK_SCHEMA["properties"]}
    fb["positives"] = [str(x) for x in (fb.get("positives") or [])][:3]
    fb["improvements"] = [str(x) for x in (fb.get("improvements") or [])][:3]
    fb.update(model=model, created_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
              type=report.get("type"), race=report.get("race"))
    row.feedback = fb
    row.feedback_status = "done"
    db.commit()
    return fb


def auto_feedback(user_id: int, activity_ids: list[int]) -> None:
    """Hintergrundaufgabe nach Import: Feedback fuer frische Fahrten ohne Feedback (eigene DB-Sitzung)."""
    if not get_settings().anthropic_api_key or not activity_ids:
        return
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            return
        cutoff = dt.datetime.now() - dt.timedelta(days=AUTO_FEEDBACK_DAYS)
        done = 0
        for aid in activity_ids:
            if done >= AUTO_FEEDBACK_MAX:
                break
            act = db.get(Activity, aid)
            if act is None or act.user_id != user_id or act.start_time.replace(tzinfo=None) < cutoff:
                continue
            row = insight_row(db, act)
            if row.feedback:
                continue
            try:
                generate_feedback(db, user, act)
                done += 1
            except InsightError as e:
                log.info("Automatisches Feedback fuer %s uebersprungen: %s", aid, e)
                if e.status == 429:
                    break
            except Exception:  # Hintergrund darf nie abstuerzen
                log.exception("Automatisches Feedback fuer %s fehlgeschlagen", aid)
                db.rollback()


# ------------------------------------------------- Einordnung der Belastung ---

LOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["too_much", "slightly_much", "ok", "too_little", "mixed", "unknown"]},
        "text": {"type": "string", "description": "Hoechstens zwei Saetze, hoechstens 260 Zeichen"},
    },
    "required": ["verdict", "text"],
    "additionalProperties": False,
}

LOAD_PROMPT = """Du bist der persoenliche Radtrainer des Athleten. Ordne fuer die Uebersichtsseite der App ein, ob die aktuelle \
Trainingsbelastung zu hoch, passend oder zu gering ist. Deutsch, per Du (Du, Dein, Dich gross), konkret, hoechstens zwei Saetze, kein Markdown.

Grundlage ist die automatische Belastungsbewertung (Urteil und Hinweise). Pruefe sie gegen Gedaechtnis, Gespraech, Ziele und Saisonplan:
- Bewusste Pause, Offseason, Uebergang, Tapering, Krankheit oder Verletzung: sinkende Fitness und hohe Form sind dann gewollt. \
Das Urteil ist dann ok, nicht too_little, und der Text sagt das.
- Sonst uebernimm das Urteil der Bewertung, ausser die Daten zeigen klar etwas anderes.
- Nenne die ein bis zwei wichtigsten Gruende mit Zahl und, wenn noetig, was zu tun ist. Erfinde keine Zahlen oder Termine.
Schwellen wie CTL-Anstieg oder Monotonie sind Praxisregeln, keine Studienergebnisse."""

_load_cache: dict[int, tuple[tuple, dict]] = {}


def coach_load_view(db: Session, user: User, report: dict, *, client: Any = None, today: dt.date | None = None) -> dict | None:
    """Einordnung der Belastung durch den Coach (beruecksichtigt Gedaechtnis und Gespraech); None ohne Coach oder bei Fehlern."""
    from .coach.agent import _client, _stream, build_context
    from .coach.form_hint import _chat_lines
    from .coach.tools import active_memories, memory_line

    settings = get_settings()
    if client is None and not settings.anthropic_api_key:
        return None
    today = today or dt.date.today()
    chat, last_id = _chat_lines(db, user)
    memories = tuple(memory_line(m) for m in active_memories(db, user.id, today))
    key = (today, report["verdict"], tuple(f["code"] for f in report["flags"]), memories, last_id, user.profile.goals or "")
    hit = _load_cache.get(user.id)
    if hit and hit[0] == key:
        return hit[1]
    prompt = "\n".join([
        build_context(db, user, today), "",
        "Automatische Belastungsbewertung (JSON):", json.dumps(report, ensure_ascii=False), "",
        "Letzter Teil des Gespraechs (aelteste zuerst):", *(chat or ["(noch kein Gespraech)"]), "",
        "Ordne die Belastung jetzt ein.",
    ])
    try:
        final = _stream(client or _client(settings), dict(
            model=settings.coach_chat_model, max_tokens=3000, system=LOAD_PROMPT,
            messages=[{"role": "user", "content": prompt}], thinking={"type": "adaptive"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": LOAD_SCHEMA}},
        ), False)
        data = json.loads("".join(b.text for b in final.content if b.type == "text"))
    except (anthropic.APIError, OSError, ValueError) as e:
        log.warning("Einordnung der Belastung nicht erzeugt: %s", e)
        return None
    if not isinstance(data, dict) or data.get("verdict") not in LOAD_SCHEMA["properties"]["verdict"]["enum"] or not data.get("text"):
        return None
    view = {"verdict": data["verdict"], "text": str(data["text"]).strip()[:400]}
    _load_cache[user.id] = (key, view)
    return view
