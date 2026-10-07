"""Automatische FTP-Anpassung: Entscheidungsregeln, Wirkung, Mitteilung im Chat, Rueckgaengig und Profil."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import insights as I
from app.db import Base, SessionLocal, engine
from app.main import app
from app.metrics import analysis as AN
from app.models import Activity, ActivityInsight, AtpWeek, CoachMessage, FtpChange, PlannedWorkout, User
from test_coach import make_user

FTP = 260.0
TODAY = dt.date.today()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def series(*blocks):
    out = []
    for secs, w in blocks:
        out += [float(w)] * secs
    return out


def raise_assessment(estimate=290, estimators=3, spread=0.03):
    return {"recommendation": "raise", "estimate": estimate, "estimators": estimators, "spread": spread}


def decide(ftp=FTP, assessment=None, **kw):
    return AN.ftp_auto_decision(ftp, assessment or raise_assessment(), today=TODAY, **kw)


# ---------------------------------------------------------------- Regeln ---


def test_decision_raises_only_with_clear_data_and_caps_the_step():
    d = decide()
    assert d["apply"] and d["new_ftp"] == 270 and d["capped"]  # +5 % von 260 = 273 -> 270
    assert decide(assessment=raise_assessment(estimate=268))["new_ftp"] == 270 and not decide(assessment=raise_assessment(estimate=268))["capped"]
    assert not decide(assessment=raise_assessment(estimate=266))["apply"]  # unter +3 % (267,8 W)
    assert not decide(assessment=raise_assessment(estimators=1))["apply"]
    assert not decide(assessment=raise_assessment(spread=0.12))["apply"]
    for rec in ("hold", "ok", "test"):
        assert not decide(assessment={**raise_assessment(), "recommendation": rec})["apply"]


def test_decision_respects_pauses_and_phase_and_never_lowers():
    d = TODAY - dt.timedelta(days=5)
    assert not decide(last_auto=d)["apply"]
    assert decide(last_auto=TODAY - dt.timedelta(days=15))["apply"]
    assert not decide(last_manual=TODAY - dt.timedelta(days=20))["apply"]
    assert decide(last_manual=TODAY - dt.timedelta(days=30))["apply"]
    assert not decide(phase_now="transition")["apply"]
    assert decide(phase_now="build")["apply"]
    low = decide(ftp=300, assessment={"recommendation": "raise", "estimate": 250, "estimators": 3, "spread": 0.0})
    assert not low["apply"]  # Schaetzung unter der FTP: nie senken


# ------------------------------------------------------ Wirkung und Chat ---


def hard_ride(db, user, days_ago=2, watts=300):
    """1 h bei hoher Leistung: ergibt mehrere uebereinstimmende Schaetzer (20, 30, 60 min, NP)."""
    w = series((600, 150), (3600, watts), (600, 120))
    a = Activity(user_id=user.id, source="fit_upload", external_id=f"hard{days_ago}", name="Harte Fahrt",
                 start_time=dt.datetime.combine(TODAY - dt.timedelta(days=days_ago), dt.time(9)), duration_s=len(w),
                 distance_m=40000, avg_power=sum(w) / len(w), norm_power=watts * 0.99, tss=100, ftp_used=FTP,
                 streams={"time": list(range(len(w))), "watts": w})
    db.add(a)
    db.commit()
    return a


def make_history(db, user, tss=70):
    for d in range(10, 60):
        db.add(Activity(user_id=user.id, source="fit_upload", external_id=f"h{d}", name="Ausfahrt",
                        start_time=dt.datetime.combine(TODAY - dt.timedelta(days=d), dt.time(9)), duration_s=3600, distance_m=30000,
                        avg_power=200, norm_power=205, tss=tss))
    db.commit()


def test_auto_adjust_raises_ftp_logs_it_writes_chat_message_and_keeps_history():
    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        make_history(db, u)
        hard_ride(db, u)
        old_tss = db.scalar(select(Activity.tss).where(Activity.external_id == "h10"))
        db.add(PlannedWorkout(user_id=u.id, date=TODAY + dt.timedelta(days=1), title="Sweetspot", planned_tss=0, structure=[
            {"type": "steady", "duration_s": 3600, "power_pct": [90, 90]}]))
        db.commit()
        uid = u.id

    res = I.auto_adjust_ftp(uid)
    assert res == {"old_ftp": 260.0, "new_ftp": 270}  # auf +5 % begrenzt

    with SessionLocal() as db:
        u = db.get(User, uid)
        assert u.profile.ftp == 270
        ch = db.scalar(select(FtpChange))
        assert (ch.old_ftp, ch.new_ftp, ch.source) == (260.0, 270.0, "coach") and ch.reason and ch.evidence
        msg = db.scalar(select(CoachMessage).where(CoachMessage.user_id == uid))
        assert msg.role == "assistant" and "von 260 auf 270 W" in msg.content["text"] and "rueckgaengig" in msg.content["text"]
        assert "5 %" in msg.content["text"] and msg.content["actions"] == ["FTP angehoben: 260 auf 270 W"]
        # kuenftiges Training neu berechnet, vergangene Fahrten unveraendert
        w = db.scalar(select(PlannedWorkout))
        assert w.planned_tss and w.planned_duration_s == 3600
        assert db.scalar(select(Activity.tss).where(Activity.external_id == "h10")) == old_tss

    assert I.auto_adjust_ftp(uid) is None  # Abstand von 14 Tagen


def test_auto_adjust_does_nothing_without_clear_data_or_in_transition():
    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        make_history(db, u)
        db.add(Activity(user_id=u.id, source="fit_upload", external_id="easy", name="Locker",
                        start_time=dt.datetime.combine(TODAY - dt.timedelta(days=1), dt.time(9)), duration_s=3600, distance_m=30000,
                        avg_power=170, norm_power=175, tss=50))
        db.commit()
        uid = u.id
    assert I.auto_adjust_ftp(uid) is None

    with SessionLocal() as db:
        u = db.get(User, uid)
        hard_ride(db, u)
        db.add(AtpWeek(user_id=uid, week_start=TODAY - dt.timedelta(days=TODAY.weekday()), phase="transition", tss_target=200))
        db.commit()
    assert I.auto_adjust_ftp(uid) is None
    with SessionLocal() as db:
        assert db.get(User, uid).profile.ftp == FTP and db.scalar(select(FtpChange)) is None and db.scalar(select(CoachMessage)) is None


def test_after_import_runs_feedback_then_adjusts(monkeypatch):
    calls = []
    monkeypatch.setattr(I, "auto_feedback", lambda uid, ids: calls.append(("fb", uid, ids)))
    monkeypatch.setattr(I, "auto_adjust_ftp", lambda uid: calls.append(("ftp", uid)))
    I.after_import(5, [1, 2])
    I.after_import(5, [])
    assert calls == [("fb", 5, [1, 2]), ("ftp", 5), ("fb", 5, [])]


# -------------------------------------------------- Profil, Rueckgaengig ---


def auth(c, email="ftp@example.com"):
    tok = c.post("/auth/register", json={"email": email, "password": "geheim123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_profile_shows_change_undo_locks_and_history():
    c = TestClient(app)
    h = auth(c)
    assert c.put("/profile", json={"ftp": FTP}, headers=h).json()["ftp"] == FTP
    with SessionLocal() as db:
        u = db.scalar(select(User))
        make_history(db, u)
        hard_ride(db, u)
        uid = u.id
    # manuelle Aenderung im Profil pausiert die Automatik 28 Tage
    assert I.auto_adjust_ftp(uid) is None
    with SessionLocal() as db:
        db.query(FtpChange).delete()
        db.commit()

    assert I.auto_adjust_ftp(uid)["new_ftp"] == 270
    p = c.get("/profile", headers=h).json()
    assert p["ftp"] == 270 and p["ftp_change"]["old_ftp"] == 260 and p["ftp_change"]["can_undo"] is True
    assert p["zones"][3]["min"] == round(0.9 * 270)

    undone = c.post("/profile/ftp/undo", headers=h).json()
    assert undone["ftp"] == 260 and undone["ftp_change"] is None
    assert c.post("/profile/ftp/undo", headers=h).status_code == 409  # nichts mehr rueckgaengig zu machen
    hist = c.get("/profile/ftp-history", headers=h).json()
    assert [x["source"] for x in hist] == ["undo", "coach"]
    assert I.auto_adjust_ftp(uid) is None  # nach Rueckgaengig ruht die Automatik

    # manuelle Aenderung wird als solche festgehalten
    c.put("/profile", json={"ftp": 262}, headers=h)
    assert c.get("/profile/ftp-history", headers=h).json()[0]["source"] == "user"
    assert c.get("/profile", headers=h).json()["ftp_change"] is None
    assert c.put("/profile", json={"weight_kg": 71}, headers=h).json()["ftp"] == 262  # ohne ftp unveraendert, kein Eintrag
    assert len(c.get("/profile/ftp-history", headers=h).json()) == 3  # coach, undo, user (kein Eintrag fuer Gewicht)


def test_activity_list_contains_feedback_headline():
    c = TestClient(app)
    h = auth(c, "list@example.com")
    with SessionLocal() as db:
        u = db.scalar(select(User))
        a = hard_ride(db, u)
        b = hard_ride(db, u, days_ago=5, watts=250)
        I.insight_row(db, a).feedback = {"headline": "Starke Fahrt"}
        db.commit()
    rows = {r["id"]: r for r in c.get("/activities", headers=h).json()}
    assert rows[a.id]["feedback_headline"] == "Starke Fahrt" and rows[b.id]["feedback_headline"] is None


def test_manual_accept_is_recorded_as_user_change():
    c = TestClient(app)
    h = auth(c, "acc@example.com")
    c.put("/profile", json={"ftp": FTP}, headers=h)
    r = c.post("/metrics/ftp-check/accept", json={"ftp": 280}, headers=h).json()
    assert r["old_ftp"] == FTP and r["ftp"] == 280
    last = c.get("/profile/ftp-history", headers=h).json()[0]
    assert last["source"] == "user" and last["new_ftp"] == 280
