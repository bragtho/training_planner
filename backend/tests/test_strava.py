import time
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, SessionLocal, engine
from app.integrations import strava
from app.main import app
from app.models import Activity, AthleteProfile, Integration, User
from app.security import create_state_token, encrypt


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _user(db, ftp=250.0) -> tuple[User, AthleteProfile]:
    u = User(email="s@example.com", password_hash="x")
    u.profile = AthleteProfile(ftp=ftp, hr_max=190, hr_rest=50, lthr=170)
    db.add(u)
    db.commit()
    return u, u.profile


def _integration(db, user, expires_in=3600) -> Integration:
    i = Integration(
        user_id=user.id, provider="strava", external_user_id="42",
        access_token_enc=encrypt("acc"), refresh_token_enc=encrypt("ref"),
        expires_at=int(time.time()) + expires_in,
    )
    db.add(i)
    db.commit()
    return i


def _ride(i, **kw) -> dict:
    d = {
        "id": i, "name": f"Ride {i}", "sport_type": "Ride", "moving_time": 3600, "distance": 30000,
        "start_date": "2026-09-01T06:00:00Z", "start_date_local": "2026-09-01T08:00:00Z",
        "total_elevation_gain": 300, "device_watts": True, "average_watts": 230,
        "weighted_average_watts": 250,
    }
    d.update(kw)
    return d


def _mock(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_activity_fields_power_tss():
    with SessionLocal() as db:
        _, p = _user(db)
        f = strava.activity_fields(_ride(1), p)
    assert abs(f["tss"] - 100.0) < 1e-6  # 1 h bei NP = FTP
    assert f["start_time"].hour == 8  # lokale Uhrzeit bleibt erhalten


def test_activity_fields_hr_fallback_and_none():
    with SessionLocal() as db:
        _, p = _user(db)
        hr = strava.activity_fields(_ride(1, device_watts=False, average_heartrate=150), p)
        none = strava.activity_fields(_ride(2, device_watts=False), p)
    assert hr["tss"] and hr["norm_power"] is None
    assert none["tss"] is None


def test_sync_imports_all_sports_and_is_idempotent():
    pages = {1: [_ride(1), {"id": 2, "sport_type": "Run", "start_date": "2026-09-02T06:00:00Z",
                             "start_date_local": "2026-09-02T08:00:00Z"}]}

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer acc"
        return httpx.Response(200, json=pages.get(int(req.url.params["page"]), []))

    with SessionLocal() as db:
        u, p = _user(db)
        integ = _integration(db, u)
        r1 = strava.sync_activities(db, integ, p, http=_mock(handler))
        r2 = strava.sync_activities(db, integ, p, full=True, http=_mock(handler))
        count = len(db.scalars(select(Activity)).all())
        cursor = integ.sync_cursor
    assert r1 == {"imported": 2, "updated": 0, "new_ids": [1, 2]}
    assert r2 == {"imported": 0, "updated": 2, "new_ids": []}
    assert count == 2
    assert cursor == int(datetime(2026, 9, 2, 6, tzinfo=timezone.utc).timestamp())


def test_expired_token_is_refreshed():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "ref2",
                                             "expires_at": int(time.time()) + 3600})
        assert req.headers["authorization"] == "Bearer new"
        return httpx.Response(200, json=[])

    with SessionLocal() as db:
        u, p = _user(db)
        integ = _integration(db, u, expires_in=-10)
        strava.sync_activities(db, integ, p, http=_mock(handler))
    assert any("/oauth/token" in c for c in calls)


def test_streams_give_exact_np():
    with SessionLocal() as db:
        u, p = _user(db)
        d = _ride(1, weighted_average_watts=None)
        strava.upsert_activity(db, u.id, d, p)
        db.commit()
        a = db.scalar(select(Activity))
        est = a.norm_power
        strava.apply_streams(a, {"time": list(range(3600)), "watts": [200] * 3600}, p)
        assert abs(a.norm_power - 200) < 1e-6 and abs(est - 230 * 1.05) < 1e-6
        assert abs(a.tss - 3600 * 200 * 0.8 / (250 * 3600) * 100) < 1e-6
        # Ein erneuter Sync darf die exakten Werte nicht mit Schaetzwerten ueberschreiben
        strava.upsert_activity(db, u.id, d, p)
        assert abs(a.norm_power - 200) < 1e-6


def test_resample_gaps():
    out = strava.resample_1hz([0, 3, 20], [100, 200, 300])
    assert out[:4] == [100, 100, 100, 200]  # Luecke 0->3 s (<= 5 s): Wert gehalten
    assert out[4] == 0 and out[10] == 0  # Luecke 3->20 s (> 5 s): als Pause = 0 W
    assert out[20] == 300


def test_webhook_delete_and_unknown_owner():
    with SessionLocal() as db:
        u, p = _user(db)
        _integration(db, u)
        strava.upsert_activity(db, u.id, _ride(7), p)
        db.commit()
        assert strava.handle_webhook_event(
            db, {"object_type": "activity", "aspect_type": "delete", "object_id": 7, "owner_id": 42}) == "deleted"
        assert db.scalar(select(Activity)) is None
        assert strava.handle_webhook_event(
            db, {"object_type": "activity", "aspect_type": "create", "object_id": 8, "owner_id": 99}) == "unknown_owner"


def test_http_api_flow():
    c = TestClient(app)
    tok = c.post("/auth/register", json={"email": "api@example.com", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    st = c.get("/integrations/strava/status", headers=h).json()
    assert st["configured"] and not st["connected"]
    url = c.get("/integrations/strava/authorize-url", headers=h).json()["url"]
    assert url.startswith("https://www.strava.com/oauth/authorize?") and "activity%3Aread_all" in url
    assert c.post("/integrations/strava/sync", headers=h).status_code == 409

    # state-Token darf nicht als Login funktionieren
    state = create_state_token(1, "strava")
    assert c.get("/profile", headers={"Authorization": f"Bearer {state}"}).status_code == 401
    assert "abgelaufen" in c.get("/integrations/strava/callback?code=x&state=kaputt").text

    # Webhook-Verifizierung
    ok = c.get("/webhooks/strava", params={"hub.mode": "subscribe", "hub.challenge": "abc", "hub.verify_token": "verify-me"})
    assert ok.json() == {"hub.challenge": "abc"}
    assert c.get("/webhooks/strava", params={"hub.mode": "subscribe", "hub.challenge": "abc", "hub.verify_token": "x"}).status_code == 403

    # PMC + Aktivitaetenliste mit Daten
    with SessionLocal() as db:
        uid = db.scalar(select(User).where(User.email == "api@example.com")).id
        prof = db.scalar(select(AthleteProfile).where(AthleteProfile.user_id == uid))
        for i, day in enumerate(("2026-09-01", "2026-09-03")):
            strava.upsert_activity(db, uid, _ride(i + 1, start_date_local=f"{day}T08:00:00Z"), prof)
        db.commit()
    acts = c.get("/activities", headers=h).json()
    assert [a["name"] for a in acts] == ["Ride 2", "Ride 1"]  # neueste zuerst
    pmc = c.get("/metrics/pmc?days=30", headers=h).json()
    assert pmc["rows"] and pmc["current"]["ctl"] > 0
    assert pmc["rows"][-1]["date"] == max(date.today(), date(2026, 9, 3)).isoformat()
    # fremde Aktivitaet ist nicht abrufbar
    tok2 = c.post("/auth/register", json={"email": "other@example.com", "password": "geheim123"}).json()["access_token"]
    assert c.get(f"/activities/{acts[0]['id']}", headers={"Authorization": f"Bearer {tok2}"}).status_code == 404


def test_hr_tss_zones_like_trainingpeaks():
    from app.metrics.power import hr_tss, hr_tss_series

    assert abs(hr_tss(3600, 170, 170) - 100) < 1e-6  # 1 h an der Schwelle (Zone 5a) = 100
    assert abs(hr_tss(3600, 150, 170) - 40) < 1e-6  # 88 % LTHR: Zone 2 (Rad)
    assert abs(hr_tss(3600, 140, 170, "run") - 20) < 1e-6  # 82 % LTHR: Zone 1 (Laufen: unter 85 %)
    assert abs(hr_tss(3600, 140, 170, "bike") - 40) < 1e-6  # gleiche HF auf dem Rad: Zone 2 (ab 81 %)
    assert hr_tss(0, 150, 170) == 0 and hr_tss(3600, 0, 170) == 0
    # Kurve: 30 min bei 100 % (50) + 30 min bei 70 % (Zone 1: 10) = 60
    t = list(range(0, 3601, 1))
    hr = [170] * 1800 + [119] * 1801
    assert abs(hr_tss_series(t, hr, 170) - 60) < 0.1
    # Luecken (hier 600 s ohne Daten) zaehlen hoechstens mit 10 s
    assert hr_tss_series([0, 600], [170, 170], 170) < 3


def test_other_sports_get_hr_tss_not_power_tss():
    with SessionLocal() as db:
        _, p = _user(db)
        run = strava.activity_fields(_ride(1, sport_type="Run", device_watts=True, average_watts=300, average_heartrate=165), p)
        hike = strava.activity_fields(_ride(2, sport_type="Hike", device_watts=False, average_heartrate=120, moving_time=7200), p)
        gym = strava.activity_fields(_ride(3, sport_type="WeightTraining", device_watts=False), p)
        p.lthr = None
        est = strava.activity_fields(_ride(4, sport_type="Run", device_watts=False, average_heartrate=165), p)
    assert run["norm_power"] is None and run["avg_power"] is None  # Laufleistung nicht mit der Rad-FTP verrechnen
    assert abs(run["tss"] - 80) < 1e-6  # 165/170 = 97 %: Zone 4 (Laufen), 1 h
    assert abs(hike["tss"] - 40) < 1e-6  # 120/170 = 71 %: Zone 1, 2 h
    assert gym["tss"] is None  # ohne Puls kein hrTSS
    assert est["tss"] is not None  # LTHR fehlt: Schaetzung aus der maximalen HF (90 % von 190 = 171)


def test_sport_helpers():
    from app.metrics.sports import is_cycling, is_run_like, is_strength

    assert is_cycling("GravelRide") and is_cycling("VirtualRide") and not is_cycling("Run")
    assert is_run_like("Hike") and not is_run_like("Ride")
    assert is_strength("WeightTraining") and not is_strength("Yoga")
