import datetime as dt

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.main import app
from app.metrics.workout import Steps, summarize, total_duration
from app.models import Activity, User

STEPS = TypeAdapter(Steps)


def steps(raw):
    return STEPS.validate_python(raw)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def leaf(t, minutes, lo, hi=None):
    return {"type": t, "duration_s": int(minutes * 60), "power_pct": [lo, hi or lo]}


def test_one_hour_at_ftp_is_100_tss():
    s = summarize(steps([leaf("steady", 60, 100)]), 250)
    assert s["duration_s"] == 3600 and abs(s["tss"] - 100) < 0.5 and s["np"] == 250


def test_repeat_expands_and_intervals_raise_np_above_average():
    raw = [leaf("warmup", 10, 50, 70), {"type": "repeat", "count": 4, "steps": [leaf("interval", 5, 120), leaf("rest", 5, 50)]}]
    st = steps(raw)
    assert total_duration(st) == 10 * 60 + 4 * 600
    s = summarize(st, 250)
    avg_pct = (10 * 60 * 60 + 4 * (300 * 120 + 300 * 50)) / total_duration(st)
    assert s["np"] / 250 * 100 > avg_pct  # NP gewichtet harte Intervalle staerker


def test_validation_rejects_bad_input():
    for bad in (
        [leaf("steady", 10, 10)],  # < 20 % FTP
        [leaf("steady", 10, 300)],  # > 250 % FTP
        [{"type": "repeat", "count": 0, "steps": [leaf("steady", 1, 80)]}],
        [{"type": "repeat", "count": 2, "steps": [{"type": "repeat", "count": 2, "steps": []}]}],  # keine Verschachtelung
        [leaf("steady", 13 * 60, 60)],  # > 12 h
        [],
    ):
        with pytest.raises(ValidationError):
            steps(bad)


def _client():
    c = TestClient(app)
    tok = c.post("/auth/register", json={"email": "p@example.com", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    c.put("/profile", json={"ftp": 250}, headers=h)
    return c, h


def test_calendar_flow():
    c, h = _client()
    today = dt.date.today()
    past, future = today - dt.timedelta(days=3), today + dt.timedelta(days=3)
    body = lambda d, **kw: {"date": d.isoformat(), "title": "Sweetspot", "structure": [leaf("steady", 60, 100)], **kw}

    done = c.post("/workouts", json=body(past), headers=h)
    assert done.status_code == 201 and abs(done.json()["planned_tss"] - 100) < 0.5
    missed = c.post("/workouts", json=body(past - dt.timedelta(days=1)), headers=h).json()
    skipped = c.post("/workouts", json=body(past - dt.timedelta(days=2), status="skipped"), headers=h).json()
    planned = c.post("/workouts", json=body(future), headers=h).json()
    rest = c.post("/workouts", json={"date": future.isoformat(), "title": "Ruhetag", "planned_tss": 0}, headers=h).json()
    assert rest["structure"] is None and rest["planned_tss"] == 0

    with SessionLocal() as db:
        uid = db.scalar(select(User).where(User.email == "p@example.com")).id
        db.add(Activity(user_id=uid, source="strava", external_id="1", name="Fahrt", sport="Ride",
                        start_time=dt.datetime.combine(past, dt.time(9)), duration_s=3600, tss=88.0))
        db.commit()

    r = c.get("/calendar", params={"start": (today - dt.timedelta(days=10)).isoformat(), "end": (today + dt.timedelta(days=10)).isoformat()}, headers=h).json()
    st = {w["id"]: w for w in r["workouts"]}
    assert st[done.json()["id"]]["status"] == "completed" and st[done.json()["id"]]["actual_tss"] == 88.0
    assert st[missed["id"]]["status"] == "missed"
    assert st[skipped["id"]]["status"] == "skipped"
    assert st[planned["id"]]["status"] == "planned"
    assert len(r["activities"]) == 1
    # zu grosser Zeitraum
    assert c.get("/calendar", params={"start": "2026-01-01", "end": "2027-01-01"}, headers=h).status_code == 422


def test_update_copy_delete_preview_and_isolation():
    c, h = _client()
    d = dt.date.today().isoformat()
    w = c.post("/workouts", json={"date": d, "title": "A", "structure": [leaf("steady", 30, 80)]}, headers=h).json()

    up = c.put(f"/workouts/{w['id']}", json={"date": d, "title": "B", "structure": [leaf("steady", 60, 100)]}, headers=h).json()
    assert up["title"] == "B" and up["planned_duration_s"] == 3600

    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    cp = c.post(f"/workouts/{w['id']}/copy", params={"date": tomorrow}, headers=h).json()
    assert cp["id"] != w["id"] and cp["date"] == tomorrow and cp["planned_tss"] == up["planned_tss"]

    pv = c.post("/workouts/preview", json={"structure": [leaf("steady", 60, 100)]}, headers=h).json()
    assert abs(pv["tss"] - 100) < 0.5
    assert c.post("/workouts/preview", json={"structure": [leaf("steady", 60, 500)]}, headers=h).status_code == 422

    tok2 = c.post("/auth/register", json={"email": "q@example.com", "password": "geheim123"}).json()["access_token"]
    h2 = {"Authorization": f"Bearer {tok2}"}
    assert c.get(f"/workouts/{w['id']}", headers=h2).status_code == 404
    assert c.delete(f"/workouts/{w['id']}", headers=h2).status_code == 404

    assert c.delete(f"/workouts/{w['id']}", headers=h).status_code == 204
    assert c.get(f"/workouts/{w['id']}", headers=h).status_code == 404
