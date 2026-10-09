from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.metrics.bests import classify, thresholds
from app.models import Activity, User
from app.routers import bests as bests_router


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    bests_router._cache.clear()


def test_classify_anchor_and_interpolation():
    assert thresholds(4) is None and classify(7200, 5) is None
    assert classify(3600, 3.0) == "hobby"
    assert classify(3600, 4.7) == "elite"
    assert classify(300, 7.0) == "worldtour"
    t = thresholds(600)  # zwischen 5 min und 60 min
    assert thresholds(3600)[0] < t[0] < thresholds(300)[0]


def _setup():
    c = TestClient(app)
    c.post("/auth/register", json={"email": "b@d.de", "password": "geheim123"})
    token = c.post("/auth/login", json={"email": "b@d.de", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    c.put("/profile", json={"weight_kg": 70}, headers=h)
    with SessionLocal() as db:
        uid = db.query(User).one().id
        for i, (day, w) in enumerate([(datetime(2026, 1, 10, 8), 200), (datetime(2026, 9, 1, 8), 300)]):
            db.add(Activity(user_id=uid, source="strava", external_id=str(i), sport="Ride", name=f"r{i}", start_time=day,
                            duration_s=600, distance_m=1, avg_power=w,
                            streams={"time": list(range(600)), "watts": [w] * 600}))
        db.commit()
    return c, h


def test_bests_period_and_level():
    c, h = _setup()
    r = c.get("/metrics/bests?durations=60,300", headers=h).json()
    e = {x["duration_s"]: x for x in r["efforts"]}
    assert e[60]["watts"] == 300 and e[60]["date"] == "2026-09-01"
    assert e[60]["wkg"] == pytest.approx(4.29, abs=0.01) and e[60]["level"] == "hobby"
    old = c.get("/metrics/bests?durations=60&end=2026-06-30", headers=h).json()["efforts"]
    assert old[0]["watts"] == 200
    assert c.get("/metrics/bests?durations=0", headers=h).status_code == 422


def test_thresholds_fall_monotonic_and_hyperbolic():
    ds = [5, 10, 15, 30, 60, 90, 120, 300, 600, 1200, 1800, 3600]
    rows = [thresholds(d) for d in ds]
    for a, b in zip(rows, rows[1:]):
        assert all(x > y for x, y in zip(a, b))
    elite = {d: t[1] for d, t in zip(ds, rows)}
    assert elite[300] == pytest.approx(5.5) and elite[3600] == pytest.approx(4.6)
    assert 4.7 < elite[1200] < 5.0  # 20 min liegt knapp ueber der FTP
