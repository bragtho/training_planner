"""Analyse von Fahrten, Belastung und FTP (reine Funktionen) sowie Endpunkte, Feedback und Coach-Werkzeuge."""

import datetime as dt
import json
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import insights as I
from app.coach import tools as T
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.metrics import analysis as AN
from app.models import Activity, ActivityInsight, AtpWeek, PlannedWorkout, SeasonEvent, User
from test_coach import FakeClient, make_user, msg, text

FTP = 260.0
TODAY = dt.date.today()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    I._load_cache.clear()


def series(*blocks):
    """[(sekunden, watt), ...] -> 1-Hz-Reihe"""
    out = []
    for secs, w in blocks:
        out += [float(w)] * secs
    return out


def interval_ride(work_w=300, n=5, lead=600):
    blocks = [(lead, 150)]
    for _ in range(n):
        blocks += [(240, work_w), (240, 140)]
    return series(*blocks, (600, 140))


# ------------------------------------------------------------- Einzelfahrt ---


def test_ride_metrics_detects_intervals_and_classifies_vo2():
    w = interval_ride()
    m = AN.ride_metrics(w, None, FTP)
    assert m["effort_count"] == 5 and all(e["pct_ftp"] == 115 for e in m["efforts"])
    assert m["mmp"]["180"] == 300 and m["zones_s"][4] == 5 * 240  # Z5 VO2max
    assert AN.classify(m["zones_s"], m["intensity"], m["efforts"], False) == "vo2max"
    assert AN.classify(m["zones_s"], m["intensity"], m["efforts"], True) == "race"
    easy = AN.ride_metrics(series((3600, 140)), None, FTP)
    assert AN.classify(easy["zones_s"], easy["intensity"], easy["efforts"], False) == "recovery"
    endurance = AN.ride_metrics(series((7200, 175)), None, FTP)
    assert AN.classify(endurance["zones_s"], endurance["intensity"], endurance["efforts"], False) == "endurance"
    assert endurance["pacing"]["change_pct"] == 0


def test_decoupling_and_efficiency_factor():
    w = series((7200, 200))
    steady_hr = [140.0] * 7200
    drift_hr = [140.0] * 3600 + [154.0] * 3600
    assert AN.ride_metrics(w, steady_hr, FTP)["decoupling_pct"] == 0
    m = AN.ride_metrics(w, drift_hr, FTP)
    assert 8 < m["decoupling_pct"] < 10 and m["hr"] == {"avg": 147, "max": 154}
    assert m["ef"] == round(200 / 147, 2)


def test_plan_compliance_aligns_and_rates_each_interval():
    structure = [
        {"type": "warmup", "duration_s": 600, "power_pct": [50, 70]},
        {"type": "repeat", "count": 4, "steps": [
            {"type": "interval", "duration_s": 300, "power_pct": [105, 105]},
            {"type": "rest", "duration_s": 300, "power_pct": [50, 50]},
        ]},
        {"type": "cooldown", "duration_s": 600, "power_pct": [60, 40]},
    ]
    target = FTP * 1.05
    # Fahrer startet 2 min spaeter, letztes Intervall deutlich zu schwach
    w = series((120, 100), (600, 150), (300, target), (300, 130), (300, target), (300, 130),
               (300, target * 1.1), (300, 130), (300, target * 0.85), (300, 130), (600, 120))
    c = AN.plan_compliance(structure, FTP, w, planned_tss=80, actual_tss=76, planned_duration_s=3600, actual_duration_s=3720)
    assert c["offset_s"] == 120 and c["interval_count"] == 4
    assert [i["status"] for i in c["intervals"]] == ["ok", "ok", "over", "under"]
    assert c["hit"] == 2 and c["under"] == 1 and c["over"] == 1
    assert c["tss"] == {"planned": 80, "actual": 76, "pct": 95} and c["duration"]["pct"] == 103
    assert c["fade_pct"] < 0
    assert AN.plan_compliance(None, FTP, w) is None
    assert AN.plan_compliance(None, FTP, None, planned_tss=50, actual_tss=40)["tss"]["pct"] == 80


def test_race_detection_and_personal_bests():
    assert AN.is_race("Morning Ride", 11, False, 0.7)
    assert AN.is_race("Ausfahrt", None, True, 0.6)
    assert AN.is_race("Kriterium Wien", None, False, 0.92)
    assert not AN.is_race("Race pace intervals locker", None, False, 0.6)
    pbs = AN.personal_bests({"300": 330, "1200": 280}, [{"mmp": {"300": 320, "1200": 290}}, {"mmp": {}}])
    assert pbs == [{"duration": "5 min", "watts": 330, "previous": 320, "gain_pct": 3.1}]


# --------------------------------------------------------------- Belastung ---


def pmc(loads):
    from app.metrics.load import compute_pmc

    start = TODAY - dt.timedelta(days=len(loads) - 1)
    return compute_pmc({start + dt.timedelta(days=i): v for i, v in enumerate(loads)}, start=start, end=TODAY)


def codes(res):
    return {f["code"] for f in res["flags"]}


def test_load_assessment_too_much_too_little_and_ok():
    assert AN.load_assessment(pmc([50] * 10), today=TODAY)["verdict"] == "unknown"

    spike = AN.load_assessment(pmc([50] * 50 + [160] * 10), today=TODAY)
    assert spike["verdict"] == "too_much" and {"ramp_high", "tsb_low"} <= codes(spike)

    steady = AN.load_assessment(pmc([0, 80, 60, 100, 0, 70, 120] * 9), today=TODAY, planned_14d=900, actual_14d=860)
    assert steady["verdict"] == "ok", steady["flags"]

    falling = AN.load_assessment(pmc([90] * 50 + [15] * 25), today=TODAY)
    assert falling["verdict"] == "too_little" and {"ctl_falling", "tsb_long_high"} <= codes(falling)
    # In der Uebergangsphase ist sinkende Fitness gewollt
    rest = AN.load_assessment(pmc([90] * 50 + [15] * 25), today=TODAY, atp_phase_now="transition")
    assert rest["verdict"] == "ok" and "transition" in codes(rest)

    missed = AN.load_assessment(pmc([0, 80, 60, 100, 0, 70, 120] * 9), today=TODAY, planned_14d=900, actual_14d=500,
                                atp_last_week={"target": 500, "actual": 300, "recovery": False})
    assert missed["verdict"] == "too_little" and {"under_plan", "under_atp"} <= codes(missed)

    ef = AN.load_assessment(pmc([0, 80, 60, 100, 0, 70, 120] * 9), today=TODAY, ef_trend_pct=-7)
    assert ef["verdict"] == "slightly_much" and "ef_drop" in codes(ef)


def test_ef_trend():
    rides = [{"date": TODAY - dt.timedelta(days=d), "ef": 1.40} for d in (20, 25, 30, 35)]
    rides += [{"date": TODAY - dt.timedelta(days=d), "ef": 1.30} for d in (2, 6)]
    assert AN.ef_trend(rides, TODAY) == -7.1
    assert AN.ef_trend(rides[:4], TODAY) is None


# ------------------------------------------------------------------- FTP ---


def ride(days_ago, mmp=None, np_=None, duration_s=3600, name="Fahrt"):
    return {"date": TODAY - dt.timedelta(days=days_ago), "name": name, "duration_s": duration_s, "np": np_, "mmp": mmp}


def test_ftp_assessment_raise_ok_test():
    up = AN.ftp_assessment(FTP, [ride(10, {"1200": 300, "300": 340, "180": 360, "600": 320})], TODAY)
    assert up["recommendation"] == "raise" and up["suggested_ftp"] == 280 and up["confidence"] == "high"  # Median aus 20 min und CP
    assert up["best_efforts"]["20 min"]["watts"] == 300 and up["critical_power"]["cp"] > 280

    # Lange Fahrt mit NP ueber der FTP genuegt auch ohne Sensordaten
    long_np = AN.ftp_assessment(FTP, [ride(5, None, np_=275, duration_s=4000)], TODAY)
    assert long_np["recommendation"] == "raise" and long_np["suggested_ftp"] == 275

    fits = AN.ftp_assessment(FTP, [ride(12, {"1200": 270})], TODAY)
    assert fits["recommendation"] == "ok"

    old = AN.ftp_assessment(FTP, [ride(70, {"1200": 320}), ride(3, {"1200": 200})], TODAY)
    assert old["recommendation"] == "test"  # alte Bestwerte (ueber 6 Wochen) reichen fuer eine Anhebung nicht
    assert AN.ftp_assessment(FTP, [], TODAY)["recommendation"] == "test"


def test_critical_power_needs_enough_points():
    assert AN.critical_power({180: 400, 300: 350}) is None
    cp = AN.critical_power({180: 400, 300: 350, 720: 310, 1200: 295})
    assert 270 < cp["cp"] < 300 and cp["w_prime_kj"] > 5


# ------------------------------------------------- DB, Endpunkte, Werkzeuge ---


def add_activity(db, user, day, watts=None, hr=None, *, name="Fahrt", tss=None, np_=None, source="fit_upload", ext="1"):
    streams = None
    if watts:
        streams = {"time": list(range(len(watts))), "watts": watts}
        if hr:
            streams["heartrate"] = hr
    a = Activity(user_id=user.id, source=source, external_id=ext, name=name,
                 start_time=dt.datetime.combine(day, dt.time(9)), duration_s=len(watts) if watts else 3600,
                 distance_m=30000, avg_power=(sum(watts) / len(watts)) if watts else (np_ or None), norm_power=np_,
                 tss=tss, streams=streams)
    db.add(a)
    db.commit()
    return a


def auth(c, email="ana@example.com"):
    tok = c.post("/auth/register", json={"email": email, "password": "geheim123"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_activity_analysis_endpoint_with_plan_and_race(monkeypatch):
    c = TestClient(app)
    h = auth(c)
    c.put("/profile", json={"ftp": FTP}, headers=h)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        structure = [{"type": "warmup", "duration_s": 600, "power_pct": [50, 70]},
                     {"type": "repeat", "count": 5, "steps": [{"type": "interval", "duration_s": 240, "power_pct": [115, 115]},
                                                              {"type": "rest", "duration_s": 240, "power_pct": [54, 54]}]},
                     {"type": "cooldown", "duration_s": 600, "power_pct": [55, 50]}]
        db.add(PlannedWorkout(user_id=u.id, date=TODAY, title="5x4 VO2max", structure=structure, planned_tss=85,
                              planned_duration_s=3600))
        a = add_activity(db, u, TODAY, interval_ride(work_w=FTP * 1.15), tss=82)
        b = add_activity(db, u, TODAY - dt.timedelta(days=1), series((3600, 250)), name="Ausfahrt", tss=90, ext="2")
        db.add(SeasonEvent(user_id=u.id, date=TODAY - dt.timedelta(days=1), name="Kriterium", priority="B"))
        db.commit()
        aid, bid = a.id, b.id

    r = c.get(f"/activities/{aid}/analysis", headers=h).json()
    assert r["type"] == "vo2max" and r["race"] is False and r["plan"]["title"] == "5x4 VO2max"
    assert r["compliance"]["interval_count"] == 5 and r["compliance"]["hit"] == 5
    assert r["metrics"]["zones"][4]["min"] == 20 and r["metrics"]["best_powers"]["3 min"] == 299
    assert r["feedback"] is None and r["feedback_status"] == "none"
    race = c.get(f"/activities/{bid}/analysis", headers=h).json()
    assert race["race"] is True and race["event"] == {"name": "Kriterium", "priority": "B"} and race["type"] == "race"
    # Bestwerte: die Intervallfahrt ist am Folgetag bei 3 min besser als das Rennen
    assert any(p["duration"] == "3 min" for p in r["personal_bests_90d"])

    h2 = auth(c, "fremd@example.com")
    assert c.get(f"/activities/{aid}/analysis", headers=h2).status_code == 404


FEEDBACK = {"headline": "Intervalle sauber getroffen", "summary": "Alle fuenf Intervalle lagen im Ziel.", "execution": "as_planned",
            "load_fit": "fits", "positives": ["Gleichmaessig", "Gut dosiert", "Stark", "zu viel"], "improvements": [],
            "next": "Morgen locker.", "ftp_hint": ""}


def test_feedback_is_generated_once_cached_and_limited(monkeypatch):
    monkeypatch.setattr(I, "coach_load_view", lambda *a, **k: None)  # Einordnung separat getestet
    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        a = add_activity(db, u, TODAY, interval_ride(work_w=FTP * 1.15), tss=82)
        fake = FakeClient(msg(text(json.dumps(FEEDBACK))), msg(text(json.dumps({**FEEDBACK, "headline": "Neu"}))))
        fb = I.generate_feedback(db, u, a, client=fake)
        assert fb["headline"] == "Intervalle sauber getroffen" and fb["positives"] == ["Gleichmaessig", "Gut dosiert", "Stark"]
        assert fb["type"] == "vo2max" and fb["model"] == get_settings().coach_chat_model
        call = fake.calls[0]
        assert call["output_config"]["format"]["type"] == "json_schema"
        prompt = call["messages"][0]["content"]
        assert "Analyse der Fahrt" in prompt and "FTP-Pruefung" in prompt and "Belastungsbewertung" in prompt
        # gespeichert: kein zweiter Aufruf
        assert I.generate_feedback(db, u, a, client=fake)["headline"] == "Intervalle sauber getroffen" and len(fake.calls) == 1
        assert I.generate_feedback(db, u, a, client=fake, force=True)["headline"] == "Neu"
        row = db.scalar(select(ActivityInsight))
        assert row.feedback_status == "done"

        bad = FakeClient(msg(text("kein json")))
        b = add_activity(db, u, TODAY, series((1800, 150)), ext="2")
        with pytest.raises(I.InsightError):
            I.generate_feedback(db, u, b, client=bad)
        assert I.insight_row(db, b).feedback_status == "failed"

        monkeypatch.setattr(get_settings(), "coach_feedback_daily_limit", 1)
        with pytest.raises(I.InsightError) as e:
            I.generate_feedback(db, u, b, client=FakeClient(msg(text(json.dumps(FEEDBACK)))))
        assert e.value.status == 429


def test_feedback_endpoint_and_auto_feedback(monkeypatch):
    monkeypatch.setattr(I, "coach_load_view", lambda *a, **k: None)
    c = TestClient(app)
    h = auth(c)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        a = add_activity(db, u, TODAY, series((1800, 150)))
        old = add_activity(db, u, TODAY - dt.timedelta(days=10), series((1800, 150)), ext="2")
        aid, old_id, uid = a.id, old.id, u.id
    assert c.post(f"/activities/{aid}/feedback", headers=h).status_code == 503  # kein API-Schluessel

    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "sk-test")
    fake = FakeClient(*[msg(text(json.dumps(FEEDBACK))) for _ in range(3)])
    monkeypatch.setattr("app.coach.agent._client", lambda settings=None: fake)
    r = c.post(f"/activities/{aid}/feedback", headers=h)
    assert r.status_code == 200 and r.json()["feedback"]["headline"] == FEEDBACK["headline"]
    assert c.get(f"/activities/{aid}/analysis", headers=h).json()["feedback"]["headline"] == FEEDBACK["headline"]

    # Hintergrund: nur frische Fahrten ohne Feedback
    I.auto_feedback(uid, [aid, old_id])
    assert len(fake.calls) == 1
    with SessionLocal() as db:
        assert I.insight_row(db, db.get(Activity, old_id)).feedback is None


def test_load_and_ftp_endpoints_and_accept(monkeypatch):
    c = TestClient(app)
    h = auth(c)
    c.put("/profile", json={"ftp": FTP}, headers=h)
    with SessionLocal() as db:
        u = db.scalar(select(User))
        for i in range(30):
            add_activity(db, u, TODAY - dt.timedelta(days=i), series((3600, 180)), tss=60, np_=180, ext=f"r{i}")
        add_activity(db, u, TODAY - dt.timedelta(days=3), series((600, 150), (1200, 305), (600, 150)), tss=95, np_=270, ext="test")
        db.add(AtpWeek(user_id=u.id, week_start=TODAY - dt.timedelta(days=TODAY.weekday()), phase="build", tss_target=450))
        db.commit()
    load = c.get("/metrics/load-check", headers=h).json()
    assert load["verdict"] in ("ok", "slightly_much", "too_much", "too_little", "mixed")
    assert load["context"]["season_phase"] == "Aufbau" and load["intensity_distribution_28d"]["rides_with_data"] >= 1

    ftp = c.get("/metrics/ftp-check", headers=h).json()
    assert ftp["recommendation"] == "raise" and ftp["suggested_ftp"] == 290
    r = c.post("/metrics/ftp-check/accept", json={"ftp": ftp["suggested_ftp"]}, headers=h).json()
    assert r["old_ftp"] == FTP and r["ftp"] == 290 and r["recomputed"] == 31
    assert c.get("/profile", headers=h).json()["ftp"] == 290
    assert c.get("/metrics/ftp-check", headers=h).json()["recommendation"] == "ok"
    assert c.post("/metrics/ftp-check/accept", json={"ftp": 20}, headers=h).status_code == 422


def test_metrics_are_recomputed_after_ftp_change():
    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        a = add_activity(db, u, TODAY, series((1800, 260)))
        assert I.metrics_for(db, u, a)["intensity"] == 1.0
        u.profile.ftp = 300.0
        db.commit()
        assert I.metrics_for(db, u, a)["intensity"] == 0.87


def test_coach_tools_analysis_load_ftp():
    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        a = add_activity(db, u, TODAY - dt.timedelta(days=1), interval_ride(), tss=80)
        add_activity(db, u, TODAY, series((3600, 160)), tss=45, ext="2")
        latest = T.HANDLERS["get_activity_analysis"](db, u, {})
        assert latest["activity"]["date"] == TODAY.isoformat()
        by_date = T.HANDLERS["get_activity_analysis"](db, u, {"date": (TODAY - dt.timedelta(days=1)).isoformat()})
        assert by_date["activity"]["id"] == a.id and by_date["type"] == "vo2max"
        assert T.HANDLERS["get_activity_analysis"](db, u, {"activity_id": a.id})["activity"]["id"] == a.id
        with pytest.raises(T.ToolError):
            T.HANDLERS["get_activity_analysis"](db, u, {"activity_id": 9999})
        with pytest.raises(T.ToolError):
            T.HANDLERS["get_activity_analysis"](db, u, {"date": "2001-01-01"})
        assert T.HANDLERS["get_load_assessment"](db, u, {})["verdict"] == "unknown"
        assert T.HANDLERS["get_ftp_assessment"](db, u, {})["recommendation"] in ("raise", "ok", "test")
        assert T.HANDLERS["get_recent_activities"](db, u, {})["activities"][0]["id"]
        assert {"get_activity_analysis", "get_load_assessment", "get_ftp_assessment"}.isdisjoint(T.WRITE_TOOLS)


def test_strava_import_remembers_race_flag_and_cleans_up():
    from app.integrations import strava

    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        d = {"id": 77, "name": "Sonntag", "type": "Ride", "sport_type": "Ride", "start_date": f"{TODAY}T08:00:00Z",
             "start_date_local": f"{TODAY}T09:00:00Z", "moving_time": 3600, "distance": 40000, "workout_type": 11,
             "device_watts": True, "average_watts": 250, "weighted_average_watts": 265}
        strava.upsert_activity(db, u.id, d, u.profile)
        db.commit()
        act = db.scalar(select(Activity))
        assert I.insight_row(db, act, create=False).workout_type == 11 and I.race_flag(db, u, act)
        db.add(__import__("app.models", fromlist=["Integration"]).Integration(
            user_id=u.id, provider="strava", external_user_id="9", access_token_enc="x", refresh_token_enc="y", expires_at=0))
        db.commit()
        assert strava.handle_webhook_event(db, {"object_type": "activity", "owner_id": 9, "object_id": 77, "aspect_type": "delete"}) == "deleted"
        assert db.scalar(select(ActivityInsight)) is None and db.scalar(select(Activity)) is None


def test_ftp_assessment_holds_after_detraining_and_ignores_easy_long_rides():
    rides = [ride(21, {"1200": 300, "1800": 285, "3600": 270}, np_=275, duration_s=3700)]
    ctl = {TODAY - dt.timedelta(days=21): 100.0, TODAY: 80.0}
    held = AN.ftp_assessment(FTP, rides, TODAY, ctl)
    assert held["recommendation"] == "hold" and "20 %" in held["reason"] and "suggested_ftp" not in held
    assert AN.ftp_assessment(FTP, rides, TODAY, {TODAY - dt.timedelta(days=21): 100.0, TODAY: 95.0})["recommendation"] == "raise"
    # Lockere lange Fahrten (60 min bei 180 W) ziehen die Schaetzung nicht herunter
    mixed = [ride(5, {"1200": 305}), ride(6, {"3600": 180, "1800": 185}, np_=185, duration_s=3600)]
    assert AN.ftp_assessment(FTP, mixed, TODAY)["suggested_ftp"] == 290


def test_coach_load_view_uses_memory_and_is_cached(monkeypatch):
    from app.models import CoachMemory

    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        db.add(CoachMemory(user_id=u.id, text="Offseason bis 01.11.2026, danach strukturiertes Training.", valid_until=TODAY + dt.timedelta(days=20)))
        db.commit()
        report = {"verdict": "too_little", "flags": [{"code": "ctl_falling", "level": "warn", "text": "x", "kind": "too_little"}],
                  "metrics": {}, "context": {}}
        fake = FakeClient(msg(text(json.dumps({"verdict": "ok", "text": "Deine Offseason ist gewollt."}))))
        view = I.coach_load_view(db, u, report, client=fake)
        assert view == {"verdict": "ok", "text": "Deine Offseason ist gewollt."}
        prompt = fake.calls[0]["messages"][0]["content"]
        assert "Offseason bis 01.11.2026" in prompt and "too_little" in prompt
        assert fake.calls[0]["output_config"]["format"]["schema"]["properties"]["verdict"]["enum"][0] == "too_much"
        assert I.coach_load_view(db, u, report, client=fake) == view and len(fake.calls) == 1  # Zwischenspeicher
        broken = FakeClient(msg(text('{"verdict": "super", "text": "x"}')))
        assert I.coach_load_view(db, u, {**report, "verdict": "ok"}, client=broken) is None
        assert I.coach_load_view(db, u, {**report, "verdict": "mixed"}) is None  # ohne API-Schluessel kein Aufruf


def test_plan_compliance_aligns_when_ride_is_shorter_than_plan():
    structure = [
        {"type": "warmup", "duration_s": 900, "power_pct": [50, 75]},
        {"type": "repeat", "count": 2, "steps": [
            {"type": "interval", "duration_s": 1200, "power_pct": [95, 100]},
            {"type": "rest", "duration_s": 480, "power_pct": [55, 55]},
        ]},
        {"type": "cooldown", "duration_s": 600, "power_pct": [60, 45]},
    ]
    # 4 min spaeter losgelegt, Ausfahren verkuerzt: Fahrt ist kuerzer als der Plan
    w = series((240, 120), (900, 160), (1200, 255), (480, 140), (1200, 250), (300, 120))
    c = AN.plan_compliance(structure, FTP, w)
    assert c["offset_s"] == 240 and [i["status"] for i in c["intervals"]] == ["ok", "ok"]


def test_coach_context_lists_recent_feedback():
    from app.coach.agent import build_context

    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        a = add_activity(db, u, TODAY, series((1800, 150)), name="Lockere Runde")
        assert "letztes Feedback" not in build_context(db, u)
        row = I.insight_row(db, a)
        row.feedback = {**FEEDBACK, "headline": "Locker und richtig dosiert"}
        db.commit()
        ctx = build_context(db, u)
        assert f"Lockere Runde (id {a.id}): Locker und richtig dosiert" in ctx


def test_feedback_prompt_carries_memory_chat_and_coach_view():
    from app.models import CoachMemory, CoachMessage

    with SessionLocal() as db:
        u = make_user(db, ftp=FTP)
        db.add(CoachMemory(user_id=u.id, text="Offseason bis 01.11.2026, danach strukturiertes Training.",
                           valid_until=TODAY + dt.timedelta(days=20)))
        db.add(CoachMessage(user_id=u.id, role="user", content={"text": "Ich pausiere bewusst bis November."}))
        for d in range(30):
            add_activity(db, u, TODAY - dt.timedelta(days=d + 1), series((3600, 180)), tss=60, np_=180, ext=f"h{d}")
        a = add_activity(db, u, TODAY, series((1800, 150)), ext="today")
        fake = FakeClient(msg(text(json.dumps({"verdict": "ok", "text": "Die Offseason ist gewollt."}))), msg(text(json.dumps(FEEDBACK))))
        I.generate_feedback(db, u, a, client=fake)
        assert len(fake.calls) == 2  # Einordnung, dann Feedback
        prompt = fake.calls[1]["messages"][0]["content"]
        assert "Offseason bis 01.11.2026" in prompt and "Ich pausiere bewusst bis November." in prompt
        assert "Die Offseason ist gewollt." in prompt and "hat Vorrang" in prompt
        assert "nie mehr Umfang" in fake.calls[1]["system"]
