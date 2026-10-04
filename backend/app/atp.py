"""Saisonplan (ATP, Annual Training Plan) wie in TrainingPeaks: Wochenziele je Trainingsphase und Wettkaempfe.

Gemeinsam genutzt von der API (manuelles Bearbeiten in der App) und vom Coach (Werkzeuge). Aus den Wochenzielen
wird eine Prognose fuer CTL/ATL/TSB berechnet, damit sich pruefen laesst, ob der Plan zum Event die richtige Form liefert.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .metrics.fitness import daily_tss
from .metrics.load import compute_pmc
from .models import Activity, AtpWeek, PlannedWorkout, SeasonEvent

PHASES = {
    "preparation": "Vorbereitung",
    "base": "Grundlage",
    "build": "Aufbau",
    "peak": "Spitze",
    "race": "Wettkampf",
    "transition": "Übergang",
}
PRIORITIES = ("A", "B", "C")
MAX_WEEKS_PER_CALL = 80
MAX_EVENTS = 40
MAX_TSS = 3000
MAX_HOURS = 60
PAST_DAYS = 400  # so weit zurueck und
FUTURE_DAYS = 800  # so weit voraus darf geplant werden
RAMP_WARN = 8.0  # CTL-Zuwachs pro Woche, ab dem gewarnt wird
JUMP_WARN = 1.3  # Wochenziel mehr als 30 % ueber der Vorwoche
FORM_RANGE = (5, 25)  # empfohlene Form (TSB) am A-Event
MAX_LOADING_WEEKS = 4  # so viele Belastungswochen ohne Entlastung am Stueck


class AtpError(ValueError):
    """Ungueltige Eingabe; die Meldung ist fuer Nutzer oder Modell gedacht."""


def monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _date(v: Any, name: str, today: dt.date) -> dt.date:
    try:
        d = dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise AtpError(f"{name}: '{v}' ist kein Datum im Format YYYY-MM-DD")
    if not today - dt.timedelta(days=PAST_DAYS) <= d <= today + dt.timedelta(days=FUTURE_DAYS):
        raise AtpError(f"{name}: {d.isoformat()} liegt ausserhalb des planbaren Zeitraums")
    return d


def _num(v: Any, name: str, lo: float, hi: float, required: bool = True) -> float | None:
    if v is None or v == "":
        if required:
            raise AtpError(f"{name} fehlt")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise AtpError(f"{name} muss eine Zahl sein")
    if not lo <= v <= hi:
        raise AtpError(f"{name} muss zwischen {lo:g} und {hi:g} liegen")
    return float(v)


# ------------------------------------------------------------------ Wochen ---


def upsert_weeks(db: Session, user_id: int, items: Any, today: dt.date | None = None) -> list[dt.date]:
    """Legt Wochen an oder aktualisiert sie (alles oder nichts). Gibt die betroffenen Montage zurueck."""
    today = today or dt.date.today()
    if not isinstance(items, list) or not items:
        raise AtpError("weeks muss eine nichtleere Liste sein")
    if len(items) > MAX_WEEKS_PER_CALL:
        raise AtpError(f"Hoechstens {MAX_WEEKS_PER_CALL} Wochen je Aufruf, teile den Plan auf")
    clean: dict[dt.date, dict] = {}
    for i, w in enumerate(items):
        pre = f"weeks[{i}]"
        if not isinstance(w, dict):
            raise AtpError(f"{pre} muss ein Objekt sein")
        start = monday_of(_date(w.get("week_start"), f"{pre}.week_start", today))  # beliebiger Tag -> Montag der Woche
        phase = w.get("phase")
        if phase not in PHASES:
            raise AtpError(f"{pre}.phase muss eines von {', '.join(PHASES)} sein")
        note = " ".join(str(w.get("note") or "").split())
        if len(note) > 200:
            raise AtpError(f"{pre}.note ist laenger als 200 Zeichen")
        clean[start] = {
            "phase": phase,
            "tss_target": _num(w.get("tss_target"), f"{pre}.tss_target", 0, MAX_TSS),
            "hours_target": _num(w.get("hours_target"), f"{pre}.hours_target", 0, MAX_HOURS, required=False),
            "recovery": bool(w.get("recovery", False)),
            "note": note or None,
        }
    existing = {
        r.week_start: r for r in db.scalars(select(AtpWeek).where(AtpWeek.user_id == user_id, AtpWeek.week_start.in_(list(clean))))
    }
    for start, v in clean.items():
        row = existing.get(start) or AtpWeek(user_id=user_id, week_start=start)
        for k, val in v.items():
            setattr(row, k, val)
        db.add(row)
    db.commit()
    return sorted(clean)


def clear_weeks(db: Session, user_id: int, start: dt.date | None = None, end: dt.date | None = None) -> int:
    q = delete(AtpWeek).where(AtpWeek.user_id == user_id)
    if start:
        q = q.where(AtpWeek.week_start >= monday_of(start))
    if end:
        q = q.where(AtpWeek.week_start <= monday_of(end))
    n = db.execute(q).rowcount
    db.commit()
    return n or 0


# ------------------------------------------------------------------ Events ---


def save_event(db: Session, user_id: int, args: dict, today: dt.date | None = None) -> SeasonEvent:
    """Neues Event (gleiches Datum und gleicher Name nur einmal) oder, mit id, Aenderung eines vorhandenen."""
    today = today or dt.date.today()
    name = " ".join(str(args.get("name") or "").split())
    if not name:
        raise AtpError("name darf nicht leer sein")
    if len(name) > 120:
        raise AtpError("name ist laenger als 120 Zeichen")
    day = _date(args.get("date"), "date", today)
    priority = str(args.get("priority") or "B").upper()
    if priority not in PRIORITIES:
        raise AtpError("priority muss A, B oder C sein (A = Hauptziel)")
    notes = " ".join(str(args.get("notes") or "").split())
    if len(notes) > 300:
        raise AtpError("notes ist laenger als 300 Zeichen")
    ev = None
    if args.get("id") is not None:
        ev = db.get(SeasonEvent, args["id"]) if isinstance(args["id"], int) else None
        if ev is None or ev.user_id != user_id:
            raise AtpError("Event nicht gefunden")
    else:
        rows = list(db.scalars(select(SeasonEvent).where(SeasonEvent.user_id == user_id)))
        ev = next((r for r in rows if r.date == day and r.name.casefold() == name.casefold()), None)
        if ev is None:
            if len(rows) >= MAX_EVENTS:
                raise AtpError(f"Hoechstens {MAX_EVENTS} Events, loesche Vergangenes oder Ueberholtes")
            ev = SeasonEvent(user_id=user_id)
            db.add(ev)
    ev.date, ev.name, ev.priority, ev.notes = day, name, priority, notes or None
    db.commit()
    return ev


def delete_event(db: Session, user_id: int, event_id: Any) -> str:
    ev = db.get(SeasonEvent, event_id) if isinstance(event_id, int) else None
    if ev is None or ev.user_id != user_id:
        raise AtpError("Event nicht gefunden")
    name = ev.name
    db.delete(ev)
    db.commit()
    return name


# ---------------------------------------------------------------- Prognose ---


def _states(db: Session, user_id: int, today: dt.date) -> tuple[dict, dict]:
    """(tatsaechliche Reihe bis heute, prognostizierte Reihe aus den Wochenzielen) jeweils nach Datum."""
    daily = daily_tss(db, user_id)
    actual_rows = compute_pmc(daily, end=max(today, max(daily))) if daily else []
    actual = {r["date"]: r for r in actual_rows}
    weeks = list(db.scalars(
        select(AtpWeek).where(AtpWeek.user_id == user_id, AtpWeek.week_start >= monday_of(today)).order_by(AtpWeek.week_start)
    ))
    if not weeks:
        return actual, {}
    start = actual_rows[-1]["date"] + dt.timedelta(days=1) if actual_rows else today
    end = weeks[-1].week_start + dt.timedelta(days=6)
    if end < start:
        return actual, {}
    plan: dict[dt.date, float] = {}
    for w in weeks:
        days = [w.week_start + dt.timedelta(days=i) for i in range(7)]
        future = [d for d in days if d >= start]
        if not future:
            continue
        done = sum(daily.get(d, 0.0) for d in days if d < start)  # bereits gefahren, verteilt den Rest gleichmaessig
        for d in future:
            plan[d] = max(w.tss_target - done, 0.0) / len(future)
    ctl0, atl0 = (actual_rows[-1]["ctl"], actual_rows[-1]["atl"]) if actual_rows else (0.0, 0.0)
    sim = compute_pmc(plan, start=start, end=end, ctl0=ctl0, atl0=atl0)  # Wochen ohne Eintrag zaehlen als Ruhe
    return actual, {r["date"]: r for r in sim}


def get_plan(db: Session, user_id: int, start: dt.date, end: dt.date, today: dt.date | None = None) -> dict:
    """Lueckenlose Wochenliste von start bis end mit Plan, Soll/Ist-Last und CTL/TSB (Ist bis heute, danach Prognose)."""
    today = today or dt.date.today()
    first, last = monday_of(start), monday_of(end)
    last_day = last + dt.timedelta(days=6)
    plan = {w.week_start: w for w in db.scalars(select(AtpWeek).where(
        AtpWeek.user_id == user_id, AtpWeek.week_start >= first, AtpWeek.week_start <= last))}
    events = list(db.scalars(select(SeasonEvent).where(
        SeasonEvent.user_id == user_id, SeasonEvent.date >= first, SeasonEvent.date <= last_day).order_by(SeasonEvent.date)))
    planned: dict[dt.date, float] = {}
    for w in db.scalars(select(PlannedWorkout).where(
            PlannedWorkout.user_id == user_id, PlannedWorkout.date >= first, PlannedWorkout.date <= last_day)):
        if w.status != "skipped":
            planned[monday_of(w.date)] = planned.get(monday_of(w.date), 0.0) + (w.planned_tss or 0.0)
    done: dict[dt.date, float] = {}
    lo = dt.datetime.combine(first, dt.time.min)
    hi = dt.datetime.combine(last_day + dt.timedelta(days=1), dt.time.min)
    for a in db.scalars(select(Activity).where(Activity.user_id == user_id, Activity.start_time >= lo, Activity.start_time < hi)):
        done[monday_of(a.start_time.date())] = done.get(monday_of(a.start_time.date()), 0.0) + (a.tss or 0.0)
    actual, sim = _states(db, user_id, today)

    weeks = []
    d = first
    while d <= last:
        sunday = d + dt.timedelta(days=6)
        state = sim.get(sunday) or (actual.get(sunday) if sunday <= today else None)
        w = plan.get(d)
        weeks.append({
            "week_start": d.isoformat(),
            "phase": w.phase if w else None,
            "tss_target": w.tss_target if w else None,
            "hours_target": w.hours_target if w else None,
            "recovery": bool(w.recovery) if w else False,
            "note": w.note if w else None,
            "planned_tss": round(planned.get(d, 0.0)),
            "actual_tss": round(done.get(d, 0.0)),
            "ctl": round(state["ctl"], 1) if state else None,
            "tsb": round(state["ctl"] - state["atl"], 1) if state else None,
            "projected": sunday in sim,
        })
        d += dt.timedelta(weeks=1)

    out_events = []
    for e in events:
        row = sim.get(e.date) or actual.get(e.date)
        out_events.append({
            "id": e.id, "date": e.date.isoformat(), "name": e.name, "priority": e.priority, "notes": e.notes,
            "days_to_go": (e.date - today).days,
            "form_tsb": round(row["tsb"], 1) if row and e.date >= today else None,
        })
    return {"weeks": weeks, "events": out_events}


def full_plan(db: Session, user_id: int, today: dt.date | None = None) -> dict:
    """Ab der Vorwoche bis zum letzten Planeintrag oder Event (hoechstens 110 Wochen), z. B. fuer die Plan-Pruefung."""
    today = today or dt.date.today()
    first = monday_of(today) - dt.timedelta(weeks=1)
    last_week = db.scalar(select(func.max(AtpWeek.week_start)).where(AtpWeek.user_id == user_id))
    last_event = db.scalar(select(func.max(SeasonEvent.date)).where(SeasonEvent.user_id == user_id))
    end = max([d for d in (last_week, last_event and monday_of(last_event), first) if d])
    return get_plan(db, user_id, first, min(end, first + dt.timedelta(weeks=110)), today)


def plan_checks(plan: dict, today: dt.date | None = None) -> list[str]:
    """Hinweise zu einem Plan: zu steile Steigerung, fehlende Entlastung, Form am A-/B-Event."""
    today = today or dt.date.today()
    cur_monday = monday_of(today).isoformat()
    out: list[str] = []
    weeks = plan["weeks"]
    prev = None
    streak = 0
    for w in weeks:
        if w["phase"] is None:
            prev, streak = None, 0
            continue
        label = f"Woche ab {w['week_start']}"
        if prev is not None:
            if w["projected"] and prev["projected"] and w["ctl"] is not None and prev["ctl"] is not None:
                ramp = w["ctl"] - prev["ctl"]
                if ramp > RAMP_WARN:
                    out.append(f"{label}: CTL steigt um {ramp:.1f} (mehr als {RAMP_WARN:g} pro Woche ist riskant), Wochenziele senken.")
            if not prev["recovery"] and prev["tss_target"] and w["tss_target"] > prev["tss_target"] * JUMP_WARN and not w["recovery"]:
                out.append(f"{label}: Wochenziel {w['tss_target']:.0f} TSS ist mehr als 30 % ueber der Vorwoche ({prev['tss_target']:.0f}).")
        if w["recovery"] or w["phase"] == "transition":
            streak = 0
        else:
            streak += 1
            if streak == MAX_LOADING_WEEKS + 1:
                out.append(f"{label}: Seit {MAX_LOADING_WEEKS} Wochen keine Entlastungswoche, eine einplanen.")
        prev = w
    for e in plan["events"]:
        if e["priority"] in ("A", "B") and e["form_tsb"] is not None:
            lo, hi = FORM_RANGE
            if not lo <= e["form_tsb"] <= hi:
                out.append(f"{e['priority']}-Event '{e['name']}' ({e['date']}): Form (TSB) laut Plan {e['form_tsb']:+.0f}, "
                           f"Ziel {lo:+d} bis {hi:+d}. Last in den letzten 1-2 Wochen anpassen (Tapering).")
    return out


# ------------------------------------------------------------------ Kontext ---


def context_lines(db: Session, user_id: int, today: dt.date | None = None) -> list[str]:
    """Kurzfassung fuer den Coach-Kontext: aktuelle Woche und anstehende Events."""
    today = today or dt.date.today()
    cur = db.scalar(select(AtpWeek).where(AtpWeek.user_id == user_id, AtpWeek.week_start == monday_of(today)))
    last = db.scalar(select(AtpWeek.week_start).where(AtpWeek.user_id == user_id).order_by(AtpWeek.week_start.desc()))
    events = list(db.scalars(select(SeasonEvent).where(SeasonEvent.user_id == user_id, SeasonEvent.date >= today)
                             .order_by(SeasonEvent.date).limit(8)))
    if cur is None and last is None and not events:
        return ["- noch kein Saisonplan und keine Events angelegt"]
    lines = []
    if cur:
        hours = f", {cur.hours_target:g} h" if cur.hours_target else ""
        lines.append(f"- Aktuelle Woche (ab {cur.week_start.isoformat()}): Phase {PHASES[cur.phase]}, Ziel {cur.tss_target:.0f} TSS{hours}"
                     + (", Entlastungswoche" if cur.recovery else "") + (f", {cur.note}" if cur.note else ""))
    elif last:
        lines.append("- Fuer die aktuelle Woche gibt es keinen Plan-Eintrag")
    if last:
        lines.append(f"- Plan reicht bis zur Woche ab {last.isoformat()}")
    for e in events:
        lines.append(f"- Event {e.priority}: {e.name}, {e.date.isoformat()} (in {(e.date - today).days} Tagen) [id {e.id}]")
    return lines
