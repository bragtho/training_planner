import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import atp as A
from app.coach import agent
from app.coach import tools as T
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Activity, AthleteProfile, AtpWeek, PlannedWorkout, SeasonEvent, User

TODAY = dt.date.today()
MONDAY = A.monday_of(TODAY)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def make_user(db, email="atp@example.com") -> User:
    u = User(email=email, password_hash="x")
    u.profile = AthleteProfile(ftp=300.0)
    db.add(u)
    db.commit()
    return u


def seed_rides(db, u, tss=60.0, days=60):
    for i in range(1, days + 1):
        db.add(Activity(user_id=u.id, source="strava", external_id=str(i), sport="Ride", tss=tss, duration_s=3600,
                        start_time=dt.datetime.combine(TODAY - dt.timedelta(days=i), dt.time(8))))
    db.commit()


def week(offset, tss=400, phase="base", **kw):
    return {"week_start": (MONDAY + dt.timedelta(weeks=offset)).isoformat(), "phase": phase, "tss_target": tss, **kw}


# ----------------------------------------------------------------- Wochen ---


def test_upsert_snaps_to_monday_updates_and_is_all_or_nothing():
    with SessionLocal() as db:
        u = make_user(db)
        wednesday = (MONDAY + dt.timedelta(days=2)).isoformat()
        starts = A.upsert_weeks(db, u.id, [{"week_start": wednesday, "phase": "base", "tss_target": 400, "hours_target": 8,
                                             "recovery": True, "note": "  Entlastung  "}])
        assert starts == [MONDAY]
        row = db.scalar(select(AtpWeek))
        assert row.week_start == MONDAY and row.recovery is True and row.note == "Entlastung" and row.hours_target == 8
        A.upsert_weeks(db, u.id, [week(0, tss=450, phase="build")])  # gleiche Woche: aktualisiert, nicht doppelt
        assert db.query(AtpWeek).count() == 1 and db.scalar(select(AtpWeek)).tss_target == 450

        for bad, part in [([], "nichtleere"), ("x", "nichtleere"), ([{"phase": "base", "tss_target": 1}], "kein Datum"),
                          ([week(0, phase="sprint")], "phase"), ([week(0, tss=-1)], "zwischen"), ([week(0, tss=5000)], "zwischen"),
                          ([week(0, tss=True)], "Zahl"), ([week(0, tss="viel")], "Zahl"), ([week(0, hours_target=99)], "hours_target"),
                          ([week(0, note="x" * 201)], "200"), ([week(200)], "ausserhalb"), (["kaputt"], "Objekt"),
                          ([week(0)] * (A.MAX_WEEKS_PER_CALL + 1), "Hoechstens")]:
            with pytest.raises(A.AtpError, match=part):
                A.upsert_weeks(db, u.id, bad)
        # eine ungueltige Woche verhindert auch das Speichern der gueltigen
        with pytest.raises(A.AtpError):
            A.upsert_weeks(db, u.id, [week(1), week(2, phase="sprint")])
        assert db.query(AtpWeek).count() == 1


def test_clear_weeks_by_range_and_user():
    with SessionLocal() as db:
        a, b = make_user(db, "a@example.com"), make_user(db, "b@example.com")
        A.upsert_weeks(db, a.id, [week(i) for i in range(5)])
        A.upsert_weeks(db, b.id, [week(0)])
        assert A.clear_weeks(db, a.id, MONDAY + dt.timedelta(weeks=1), MONDAY + dt.timedelta(weeks=2, days=3)) == 2
        assert sorted(w.week_start for w in db.scalars(select(AtpWeek).where(AtpWeek.user_id == a.id))) == [
            MONDAY, MONDAY + dt.timedelta(weeks=3), MONDAY + dt.timedelta(weeks=4)]
        assert db.query(AtpWeek).filter_by(user_id=b.id).count() == 1


# ----------------------------------------------------------------- Events ---


def test_events_validation_dedup_update_limit_isolation():
    in_30 = (TODAY + dt.timedelta(days=30)).isoformat()
    with SessionLocal() as db:
        a, b = make_user(db, "a@example.com"), make_user(db, "b@example.com")
        e = A.save_event(db, a.id, {"name": "  Giro  d'Italia ", "date": in_30, "priority": "a"})
        assert e.name == "Giro d'Italia" and e.priority == "A"
        again = A.save_event(db, a.id, {"name": "giro d'italia", "date": in_30, "priority": "A"})
        assert again.id == e.id and db.query(SeasonEvent).count() == 1
        moved = A.save_event(db, a.id, {"id": e.id, "name": "Giro", "date": in_30, "priority": "B", "notes": "Etappen"})
        assert moved.id == e.id and moved.priority == "B" and moved.notes == "Etappen"

        for bad, part in [({"name": "", "date": in_30}, "leer"), ({"name": "x" * 121, "date": in_30}, "120"),
                          ({"name": "X", "date": in_30, "priority": "Z"}, "A, B oder C"), ({"name": "X", "date": "bald"}, "kein Datum"),
                          ({"name": "X", "date": in_30, "notes": "n" * 301}, "300"), ({"name": "X", "date": in_30, "id": 999}, "nicht gefunden")]:
            with pytest.raises(A.AtpError, match=part):
                A.save_event(db, a.id, bad)
        with pytest.raises(A.AtpError, match="nicht gefunden"):  # fremder Nutzer
            A.save_event(db, b.id, {"id": e.id, "name": "Mein", "date": in_30})
        with pytest.raises(A.AtpError, match="nicht gefunden"):
            A.delete_event(db, b.id, e.id)

        for i in range(A.MAX_EVENTS - 1):
            A.save_event(db, a.id, {"name": f"Rennen {i}", "date": in_30})
        with pytest.raises(A.AtpError, match="Hoechstens"):
            A.save_event(db, a.id, {"name": "Zu viel", "date": in_30})
        assert A.delete_event(db, a.id, e.id) == "Giro"


# ------------------------------------------------- Soll/Ist, Prognose, Checks ---


def test_plan_has_continuous_weeks_actuals_and_projection():
    in_21 = TODAY + dt.timedelta(days=21)
    next_monday = MONDAY + dt.timedelta(weeks=1)  # ab der naechsten Woche: unabhaengig vom heutigen Wochentag komplett Prognose
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)  # CTL etwa 43
        A.upsert_weeks(db, u.id, [week(1, tss=500), week(2, tss=700, phase="build"), week(4, tss=300, phase="peak")])  # Woche 3 fehlt
        A.save_event(db, u.id, {"name": "Tour", "date": in_21.isoformat(), "priority": "A"})
        db.add(PlannedWorkout(user_id=u.id, date=next_monday + dt.timedelta(days=1), title="Test", planned_tss=80, status="planned"))
        db.add(PlannedWorkout(user_id=u.id, date=next_monday + dt.timedelta(days=2), title="Aus", planned_tss=50, status="skipped"))
        db.commit()

        plan = A.get_plan(db, u.id, MONDAY - dt.timedelta(weeks=1), MONDAY + dt.timedelta(weeks=5))
        weeks = {w["week_start"]: w for w in plan["weeks"]}
        assert len(plan["weeks"]) == 7 and [w["week_start"] for w in plan["weeks"]] == [
            (MONDAY + dt.timedelta(weeks=i)).isoformat() for i in range(-1, 6)]  # lueckenlos
        key = lambda n: (MONDAY + dt.timedelta(weeks=n)).isoformat()  # noqa: E731
        last_week, w1, w2, gap = weeks[key(-1)], weeks[key(1)], weeks[key(2)], weeks[key(3)]
        assert last_week["phase"] is None and last_week["projected"] is False and last_week["ctl"] is not None  # Ist-Wert
        assert last_week["actual_tss"] > 0
        assert w1["phase"] == "base" and w1["tss_target"] == 500 and w1["planned_tss"] == 80  # uebersprungenes zaehlt nicht
        assert w1["projected"] and w2["projected"] and w2["ctl"] > w1["ctl"]  # 700/Woche ist mehr als der CTL traegt
        assert gap["phase"] is None and gap["ctl"] < w2["ctl"]  # Luecke zaehlt als Ruhe -> CTL sinkt
        ev = plan["events"][0]
        assert ev["priority"] == "A" and ev["days_to_go"] == 21 and ev["form_tsb"] is not None


def test_projection_without_history_starts_at_zero():
    with SessionLocal() as db:
        u = make_user(db)
        A.upsert_weeks(db, u.id, [week(0, tss=350), week(1, tss=350)])
        weeks = A.get_plan(db, u.id, MONDAY, MONDAY + dt.timedelta(weeks=1))["weeks"]
        assert weeks[0]["projected"] and 0 < weeks[0]["ctl"] < weeks[1]["ctl"] < 50


def test_plan_checks_flag_ramp_missing_recovery_and_event_form():
    in_28 = (TODAY + dt.timedelta(days=28)).isoformat()
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        A.upsert_weeks(db, u.id, [week(i, tss=900, phase="build") for i in range(6)])
        A.save_event(db, u.id, {"name": "Hauptziel", "date": in_28, "priority": "A"})
        checks = A.plan_checks(A.full_plan(db, u.id))
        text = " ".join(checks)
        assert "CTL steigt" in text and "keine Entlastungswoche" in text and "Hauptziel" in text and "Form (TSB)" in text

        # sinnvoller Plan: kaum Hinweise (Entlastung, moderat, Tapering vor dem Event)
        A.clear_weeks(db, u.id)
        A.upsert_weeks(db, u.id, [week(0, tss=420), week(1, tss=440, phase="build"), week(2, tss=300, phase="build", recovery=True),
                                  week(3, tss=330, phase="peak"), week(4, tss=150, phase="race", recovery=True)])
        ok = A.plan_checks(A.full_plan(db, u.id))
        assert not any("CTL steigt" in c or "keine Entlastungswoche" in c for c in ok)


# --------------------------------------------------------- Coach-Werkzeuge ---


def test_coach_tools_build_and_check_a_season():
    in_35 = (TODAY + dt.timedelta(days=35)).isoformat()
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        assert "noch kein Saisonplan" in agent.build_context(db, u)

        ev = T.save_season_event(db, u, {"name": "Landesmeisterschaft", "date": in_35, "priority": "A"})
        assert ev["saved"]["priority"] == "A"
        res = T.set_season_plan_weeks(db, u, {"weeks": [week(i, tss=900, phase="build") for i in range(5)]})
        assert res["saved_weeks"] == 5 and len(res["projection"]) == 5 and res["checks"]  # zu steil -> Hinweise
        assert res["events"][0]["name"] == "Landesmeisterschaft"
        assert T.action_summary("set_season_plan_weeks", {}, res) == "Saisonplan: 5 Woche(n) gespeichert"
        assert T.action_summary("save_season_event", {}, ev).startswith("Event gespeichert: Landesmeisterschaft")

        got = T.get_season_plan(db, u, {})
        assert [w["phase"] for w in got["weeks"] if w["phase"]] == ["build"] * 5 and got["checks"]

        ctx = agent.build_context(db, u)
        assert "Saisonplan (ATP)" in ctx and "Phase Aufbau, Ziel 900 TSS" in ctx and "Event A: Landesmeisterschaft" in ctx

        with pytest.raises(T.ToolError, match="Pflicht"):
            T.clear_season_plan_weeks(db, u, {"start": MONDAY.isoformat()})
        with pytest.raises(T.ToolError, match="phase"):
            T.set_season_plan_weeks(db, u, {"weeks": [week(0, phase="x")]})
        assert T.clear_season_plan_weeks(db, u, {"start": MONDAY.isoformat(), "end": (MONDAY + dt.timedelta(weeks=9)).isoformat()}) == {"deleted_weeks": 5}
        assert T.action_summary("delete_season_event", {}, T.delete_season_event(db, u, {"id": ev["saved"]["id"]})).startswith("Event geloescht")
        with pytest.raises(T.ToolError, match="nicht gefunden"):
            T.delete_season_event(db, u, {"id": 999})


def test_week_check_compares_with_season_plan_target():
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        A.upsert_weeks(db, u.id, [week(1, tss=300)])
        monday = MONDAY + dt.timedelta(weeks=1)
        res = T.create_workouts(db, u, {"workouts": [
            {"date": (monday + dt.timedelta(days=d)).isoformat(), "title": f"T{d}", "planned_duration_s": 7200, "planned_tss": 120}
            for d in range(3)]})
        chk = res["week_checks"][0]
        assert chk["atp_target_tss"] == 300 and chk["atp_phase"] == "Grundlage" and "ueber dem Wochenziel" in chk["atp_note"]


# --------------------------------------------------------------------- API ---


def test_atp_api(monkeypatch):
    c = TestClient(app)
    h1 = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "p1@example.com", "password": "geheim123"}).json()["access_token"]}
    h2 = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "p2@example.com", "password": "geheim123"}).json()["access_token"]}
    assert c.get("/atp").status_code == 401

    body = {"weeks": [{"week_start": MONDAY.isoformat(), "phase": "base", "tss_target": 400, "recovery": False, "note": "Start"}]}
    assert c.put("/atp/weeks", json=body, headers=h1).json() == {"saved": 1}
    bad = {"weeks": [{**body["weeks"][0], "phase": "sprint"}]}
    r = c.put("/atp/weeks", json=bad, headers=h1)
    assert r.status_code == 422 and "phase" in r.json()["detail"]
    assert c.put("/atp/weeks", json={"weeks": []}, headers=h1).status_code == 422

    got = c.get("/atp", headers=h1).json()
    first = next(w for w in got["weeks"] if w["phase"])
    assert first["week_start"] == MONDAY.isoformat() and first["tss_target"] == 400 and first["note"] == "Start"
    assert len(got["weeks"]) == 57  # vier Wochen zurueck bis 52 voraus, lueckenlos
    assert all(w["phase"] is None for w in c.get("/atp", headers=h2).json()["weeks"])
    assert c.get("/atp", params={"start": "2026-01-10", "end": "2026-01-01"}, headers=h1).status_code == 422

    ev = c.post("/events".replace("/events", "/atp/events"), json={"name": "Meisterschaft", "date": (TODAY + dt.timedelta(days=50)).isoformat(),
                                                                    "priority": "A"}, headers=h1)
    assert ev.status_code == 200 and ev.json()["priority"] == "A"
    eid = ev.json()["id"]
    assert c.post("/atp/events", json={"name": "X", "date": TODAY.isoformat(), "priority": "Q"}, headers=h1).status_code == 422
    upd = c.put(f"/atp/events/{eid}", json={"name": "Meisterschaft", "date": (TODAY + dt.timedelta(days=51)).isoformat(), "priority": "B"}, headers=h1)
    assert upd.json()["priority"] == "B"
    assert c.put(f"/atp/events/{eid}", json={"name": "Hack", "date": TODAY.isoformat()}, headers=h2).status_code == 404
    assert c.delete(f"/atp/events/{eid}", headers=h2).status_code == 404
    assert [e["name"] for e in c.get("/atp", headers=h1).json()["events"]] == ["Meisterschaft"]
    assert c.delete(f"/atp/events/{eid}", headers=h1).status_code == 204

    assert c.delete("/atp/weeks", params={"start": MONDAY.isoformat(), "end": MONDAY.isoformat()}, headers=h2).json() == {"deleted": 0}
    assert c.delete("/atp/weeks", params={"start": MONDAY.isoformat(), "end": MONDAY.isoformat()}, headers=h1).json() == {"deleted": 1}


def test_quick_plan_season_uses_planning_model(monkeypatch):
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "q@example.com", "password": "geheim123"}).json()["access_token"]}
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "sk-test")
    seen = []

    def fake_run(db, user, text_, history, *, model, effort, client=None):
        seen.append((text_, model, effort))
        return {"text": "ok", "actions": [], "model": model}

    monkeypatch.setattr("app.routers.coach.run_coach", fake_run)
    assert c.post("/coach/quick", json={"action": "plan_season"}, headers=h).status_code == 200
    text, model, effort = seen[0]
    assert "Saisonplan" in text and "A-Events" in text and model == s.coach_planning_model and effort == "high"
