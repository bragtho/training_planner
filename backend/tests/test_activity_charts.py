import time
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.integrations import strava
from app.main import app
from app.metrics.power import mean_max_curve
from app.models import Activity, AthleteProfile, Integration, User
from app.security import encrypt


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_mean_max_curve_finds_start():
    watts = [100.0] * 100 + [300.0] * 20 + [100.0] * 80
    pts = {p["duration_s"]: p for p in mean_max_curve(watts, [5, 20, 60, 500])}
    assert pts[5]["watts"] == 300 and 100 <= pts[5]["start_s"] <= 115
    assert pts[20] == {"duration_s": 20, "watts": 300.0, "start_s": 100}
    assert 60 in pts and pts[60]["start_s"] <= 100 + 20 - 1
    assert 500 not in pts  # laenger als die Fahrt


def _client():
    c = TestClient(app)
    c.post("/auth/register", json={"email": "c@d.de", "password": "geheim123"})
    token = c.post("/auth/login", json={"email": "c@d.de", "password": "geheim123"}).json()["access_token"]
    return c, {"Authorization": f"Bearer {token}"}


def _activity(streams):
    with SessionLocal() as db:
        u = db.query(User).one()
        a = Activity(user_id=u.id, source="strava", external_id="9", sport="Ride", name="x", start_time=datetime(2026, 9, 1, 8),
                     duration_s=200, distance_m=1000, streams=streams)
        db.add(a)
        db.add(Integration(user_id=u.id, provider="strava", external_user_id="1", access_token_enc=encrypt("a"),
                           refresh_token_enc=encrypt("r"), expires_at=int(time.time()) + 3600))
        db.commit()
        return a.id


def test_power_curve_endpoint():
    c, h = _client()
    aid = _activity({"time": list(range(200)), "watts": [100] * 100 + [300] * 100, "latlng": []})
    pts = c.get(f"/activities/{aid}/power-curve", headers=h).json()["points"]
    best = {p["duration_s"]: p for p in pts}
    assert best[60]["watts"] == 300 and best[60]["start_s"] >= 100 and best[60]["start_s"] <= 140
    assert max(best) <= 200


def test_streams_backfill_latlng_once(monkeypatch):
    c, h = _client()
    aid = _activity({"time": [0, 1], "watts": [100, 100]})
    calls = []

    def fake(self, activity_id):
        calls.append(activity_id)
        return {"time": [0, 1], "watts": [999, 999], "latlng": [[46.0, 7.0], [46.1, 7.1]]}

    monkeypatch.setattr(strava.StravaClient, "get_streams", fake)
    s = c.get(f"/activities/{aid}/streams", headers=h).json()
    assert s["latlng"] == [[46.0, 7.0], [46.1, 7.1]] and s["watts"] == [100, 100]  # Watt bleiben unveraendert
    c.get(f"/activities/{aid}/streams", headers=h)
    assert calls == ["9"]  # nur einmal bei Strava nachgeladen
