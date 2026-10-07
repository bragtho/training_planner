"""Strava-Anbindung: OAuth, Aktivitaeten-Sync, Streams.

Rate-Limits (100 Anfragen/15 min, 1000/Tag) werden geschont: Der Sync liest nur die
Aktivitaetenliste (200 pro Anfrage). Streams (1 Anfrage je Aktivitaet) werden erst bei
Bedarf geholt, z. B. beim Oeffnen einer Aktivitaet.
"""

from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..metrics.power import effective_lthr, hr_tss, hr_tss_series, intensity_factor, normalized_power, tss
from ..metrics.sports import is_cycling as sport_is_cycling, is_run_like
from ..models import Activity, AthleteProfile, Integration
from ..security import decrypt, encrypt

AUTH_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
DEAUTH_URL = "https://www.strava.com/oauth/deauthorize"
API = "https://www.strava.com/api/v3"
SCOPE = "read,activity:read_all"
STREAM_KEYS = "time,watts,heartrate,cadence,velocity_smooth,altitude,latlng"
PAGE_SIZE = 200
MAX_PAGES = 20  # Obergrenze 4000 Aktivitaeten pro Sync


class StravaError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def redirect_uri() -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/integrations/strava/callback"


def is_configured() -> bool:
    s = get_settings()
    return bool(s.strava_client_id and s.strava_client_secret)


def authorize_url(state: str) -> str:
    q = {
        "client_id": get_settings().strava_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _token_request(http: httpx.Client, data: dict) -> dict:
    s = get_settings()
    r = http.post(
        TOKEN_URL,
        data={"client_id": s.strava_client_id, "client_secret": s.strava_client_secret, **data},
    )
    if r.status_code != 200:
        raise StravaError(f"Strava-Anmeldung fehlgeschlagen ({r.status_code})", r.status_code)
    return r.json()


def exchange_code(db: Session, user_id: int, code: str, http: httpx.Client | None = None) -> Integration:
    with _client(http) as h:
        data = _token_request(h, {"code": code, "grant_type": "authorization_code"})
    integ = db.scalar(select(Integration).where(Integration.user_id == user_id, Integration.provider == "strava"))
    if integ is None:
        integ = Integration(user_id=user_id, provider="strava")
        db.add(integ)
    integ.external_user_id = str((data.get("athlete") or {}).get("id", ""))
    integ.access_token_enc = encrypt(data["access_token"])
    integ.refresh_token_enc = encrypt(data["refresh_token"])
    integ.expires_at = int(data["expires_at"])
    integ.scope = SCOPE
    db.commit()
    return integ


class _NoClose:
    """Verhindert, dass ein von aussen uebergebener (Test-)Client geschlossen wird."""

    def __init__(self, c: httpx.Client):
        self.c = c

    def __enter__(self) -> httpx.Client:
        return self.c

    def __exit__(self, *a) -> None:
        return None


def _client(http: httpx.Client | None):
    return _NoClose(http) if http is not None else httpx.Client(timeout=30)


class StravaClient:
    def __init__(self, db: Session, integ: Integration, http: httpx.Client | None = None):
        self.db = db
        self.integ = integ
        self.http = http or httpx.Client(timeout=30)

    def _access_token(self) -> str:
        if self.integ.expires_at - 60 <= time.time():
            data = _token_request(
                self.http,
                {"grant_type": "refresh_token", "refresh_token": decrypt(self.integ.refresh_token_enc)},
            )
            self.integ.access_token_enc = encrypt(data["access_token"])
            self.integ.refresh_token_enc = encrypt(data["refresh_token"])
            self.integ.expires_at = int(data["expires_at"])
            self.db.commit()
        return decrypt(self.integ.access_token_enc)

    def get(self, path: str, params: dict | None = None):
        r = self.http.get(
            f"{API}{path}", params=params, headers={"Authorization": f"Bearer {self._access_token()}"}
        )
        if r.status_code == 429:
            raise StravaError("Strava-Limit erreicht, bitte in ein paar Minuten erneut versuchen", 429)
        if r.status_code == 401:
            raise StravaError("Strava-Zugriff abgelehnt, bitte neu verbinden", 401)
        if r.status_code == 404:
            raise StravaError("Aktivitaet bei Strava nicht gefunden", 404)
        if r.status_code != 200:
            raise StravaError(f"Strava-Fehler {r.status_code}")
        return r.json()

    def list_activities(self, after: int | None, page: int) -> list[dict]:
        params = {"per_page": PAGE_SIZE, "page": page}
        if after:
            params["after"] = after
        return self.get("/athlete/activities", params)

    def get_activity(self, activity_id: int | str) -> dict:
        return self.get(f"/activities/{activity_id}")

    def get_streams(self, activity_id: int | str) -> dict[str, list]:
        data = self.get(f"/activities/{activity_id}/streams", {"keys": STREAM_KEYS, "key_by_type": "true"})
        return {k: v.get("data", []) for k, v in data.items()} if isinstance(data, dict) else {}

    def get_laps(self, activity_id: int | str) -> list[dict]:
        data = self.get(f"/activities/{activity_id}/laps")
        return data if isinstance(data, list) else []

    def deauthorize(self) -> None:
        try:
            self.http.post(DEAUTH_URL, data={"access_token": self._access_token()})
        except Exception:  # Trennen soll auch bei Strava-Problemen lokal klappen
            pass


# ---------------------------------------------------------------- Metriken ---


def is_cycling(d: dict) -> bool:
    return sport_is_cycling(d.get("sport_type") or d.get("type"))


def _hr_kind(sport: str | None) -> str:
    return "run" if is_run_like(sport) else "bike"


def _parse_dt(s: str) -> datetime:
    # start_date_local traegt faelschlich ein "Z"; wir speichern die lokale Uhrzeit,
    # damit Trainingstage der Zeitzone des Fahrers entsprechen.
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def activity_fields(d: dict, profile: AthleteProfile) -> dict:
    dur = int(d.get("moving_time") or d.get("elapsed_time") or 0)
    f: dict = dict(
        name=d.get("name"),
        sport=d.get("sport_type") or d.get("type") or "Ride",
        start_time=_parse_dt(d["start_date_local"]),
        duration_s=dur,
        distance_m=float(d.get("distance") or 0),
        elevation_m=d.get("total_elevation_gain"),
        avg_hr=d.get("average_heartrate"),
        avg_power=None, norm_power=None, intensity_factor=None, tss=None, ftp_used=None,
    )
    ftp = profile.ftp
    if is_cycling(d) and d.get("device_watts") and d.get("average_watts"):
        avg = float(d["average_watts"])
        # Falls Strava keine NP liefert: Schaetzung, wird mit Streams exakt berechnet
        np_ = float(d.get("weighted_average_watts") or avg * 1.05)
        f.update(
            avg_power=avg, norm_power=np_, intensity_factor=intensity_factor(np_, ftp),
            tss=tss(dur, np_, ftp), ftp_used=ftp,
        )
    elif d.get("average_heartrate") and effective_lthr(profile.lthr, profile.hr_max):
        # Ohne Leistungsmesser (oder andere Sportart): hrTSS wie bei TrainingPeaks, mit Streams genauer
        f["tss"] = hr_tss(dur, d["average_heartrate"], effective_lthr(profile.lthr, profile.hr_max), _hr_kind(f["sport"]))
    return f


def upsert_activity(db: Session, user_id: int, d: dict, profile: AthleteProfile) -> bool:
    """Legt die Aktivitaet an oder aktualisiert sie. True = neu angelegt."""
    ext = str(d["id"])
    act = db.scalar(
        select(Activity).where(
            Activity.user_id == user_id, Activity.source == "strava", Activity.external_id == ext
        )
    )
    fields = activity_fields(d, profile)
    created = act is None
    if created:
        act = Activity(user_id=user_id, source="strava", external_id=ext)
        db.add(act)
    elif act.streams:
        # Exakte, aus Streams berechnete Leistungswerte nicht mit Schaetzwerten ueberschreiben
        for k in ("avg_power", "norm_power", "intensity_factor", "tss", "ftp_used"):
            fields.pop(k)
    for k, v in fields.items():
        setattr(act, k, v)
    if d.get("workout_type") is not None:  # 11 = Rennen; fuer die Analyse gemerkt
        from ..insights import set_workout_type  # spaet importiert: insights nutzt dieses Modul

        db.flush()
        set_workout_type(db, act, d["workout_type"])
    return created


def sync_activities(
    db: Session, integ: Integration, profile: AthleteProfile, full: bool = False,
    http: httpx.Client | None = None,
) -> dict:
    client = StravaClient(db, integ, http)
    after = None if full else integ.sync_cursor
    newest = integ.sync_cursor or 0
    created = updated = 0
    new_ext: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        items = client.list_activities(after, page)
        if not items:
            break
        for d in items:
            newest = max(newest, int(_parse_dt(d["start_date"]).timestamp()))
            if upsert_activity(db, integ.user_id, d, profile):
                created += 1
                new_ext.append(str(d["id"]))
            else:
                updated += 1
        db.commit()
        if len(items) < PAGE_SIZE:
            break
    integ.sync_cursor = newest or None
    db.commit()
    new_ids = list(db.scalars(select(Activity.id).where(
        Activity.user_id == integ.user_id, Activity.source == "strava", Activity.external_id.in_(new_ext)))) if new_ext else []
    return {"imported": created, "updated": updated, "new_ids": new_ids}


def resample_1hz(time_s: list[int], values: list[float], max_hold_s: int = 5) -> list[float]:
    """Smart-Recording-Luecken: kurze Luecken Wert halten, laengere als 0 (Rollen/Pause)."""
    if not time_s or not values:
        return []
    out = [0.0] * (int(time_s[-1]) + 1)
    for i, t in enumerate(time_s):
        out[int(t)] = float(values[i] or 0)
        if i + 1 < len(time_s):
            gap = int(time_s[i + 1]) - int(t)
            if 1 < gap <= max_hold_s:
                for j in range(1, gap):
                    out[int(t) + j] = out[int(t)]
    return out


def parse_laps(raw: list[dict]) -> list[dict]:
    """Strava-Runden in unser Format; Startsekunde aus den aufsummierten Rundenzeiten."""
    out, start = [], 0
    for i, lap in enumerate(sorted(raw, key=lambda r: r.get("lap_index") or 0), start=1):
        dur = int(lap.get("elapsed_time") or lap.get("moving_time") or 0)
        if dur <= 0:
            continue
        out.append({
            "index": i,
            "start_s": start,
            "duration_s": dur,
            "distance_m": float(lap.get("distance") or 0),
            "avg_watts": lap.get("average_watts"),
            "avg_heartrate": lap.get("average_heartrate"),
            "avg_cadence": lap.get("average_cadence"),
            "avg_speed_ms": lap.get("average_speed"),
            "elevation_gain_m": lap.get("total_elevation_gain"),
        })
        start += dur
    return out


def apply_streams(act: Activity, streams: dict[str, list], profile: AthleteProfile) -> None:
    """Speichert Streams und berechnet NP/IF/TSS exakt neu."""
    act.streams = {**streams, "latlng": streams.get("latlng") or []}  # [] = Karte abgefragt, aber keine GPS-Daten
    ftp = profile.ftp
    watts = streams.get("watts")
    t = streams.get("time")
    lthr = effective_lthr(profile.lthr, profile.hr_max)
    if not (watts and t and sport_is_cycling(act.sport)):
        # Kein Leistungsmesser oder andere Sportart: hrTSS aus der Herzfrequenzkurve
        hr = streams.get("heartrate")
        if hr and t and lthr:
            act.tss = hr_tss_series(t, hr, lthr, _hr_kind(act.sport))
        return
    if watts and t:
        w1 = resample_1hz(t, watts)
        np_ = normalized_power(w1)
        if np_ > 0:
            dur = act.duration_s or len(w1)
            act.avg_power = sum(w1) / len(w1)
            act.norm_power = np_
            act.intensity_factor = intensity_factor(np_, ftp)
            act.tss = tss(dur, np_, ftp)
            act.ftp_used = ftp


def handle_webhook_event(db: Session, event: dict, http: httpx.Client | None = None) -> str:
    """Verarbeitet ein Strava-Webhook-Event (neue/geaenderte/geloeschte Aktivitaet)."""
    if event.get("object_type") != "activity":
        return "ignored"
    integ = db.scalar(
        select(Integration).where(
            Integration.provider == "strava", Integration.external_user_id == str(event.get("owner_id"))
        )
    )
    if integ is None:
        return "unknown_owner"
    aid = str(event["object_id"])
    if event.get("aspect_type") == "delete":
        act = db.scalar(
            select(Activity).where(
                Activity.user_id == integ.user_id, Activity.source == "strava", Activity.external_id == aid
            )
        )
        if act:
            from ..insights import delete_for

            delete_for(db, act)
            db.delete(act)
            db.commit()
        return "deleted"
    profile = db.scalar(select(AthleteProfile).where(AthleteProfile.user_id == integ.user_id))
    d = StravaClient(db, integ, http).get_activity(aid)
    upsert_activity(db, integ.user_id, d, profile)
    db.commit()
    return "upserted"
