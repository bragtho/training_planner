from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import httpx

from ..config import get_settings
from ..db import get_db
from ..integrations import strava
from ..models import Activity, Integration, User
from ..security import create_state_token, current_user, read_state_token

router = APIRouter(tags=["strava"])


def _integration(db: Session, user: User) -> Integration | None:
    return db.scalar(select(Integration).where(Integration.user_id == user.id, Integration.provider == "strava"))


def _require_connected(db: Session, user: User) -> Integration:
    integ = _integration(db, user)
    if integ is None:
        raise HTTPException(409, "Strava ist nicht verbunden")
    return integ


@router.get("/integrations/strava/status")
def status(user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = _integration(db, user)
    count = db.scalar(
        select(func.count()).select_from(Activity).where(Activity.user_id == user.id, Activity.source == "strava")
    )
    return {
        "configured": strava.is_configured(),
        "connected": integ is not None,
        "athlete_id": integ.external_user_id if integ else None,
        "activity_count": count or 0,
        "redirect_uri": strava.redirect_uri(),
    }


@router.get("/integrations/strava/authorize-url")
def authorize_url(user: User = Depends(current_user)):
    if not strava.is_configured():
        raise HTTPException(503, "STRAVA_CLIENT_ID/STRAVA_CLIENT_SECRET fehlen in backend/.env")
    return {"url": strava.authorize_url(create_state_token(user.id, "strava"))}


@router.get("/integrations/strava/callback", response_class=HTMLResponse)
def callback(
    code: str | None = None, state: str = "", error: str | None = None, db: Session = Depends(get_db)
):
    def page(title: str, text: str, status_code: int = 200) -> HTMLResponse:
        return HTMLResponse(
            f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<body style='font-family:sans-serif;max-width:30em;margin:3em auto;padding:0 1em'>"
            f"<h2>{title}</h2><p>{text}</p></body>",
            status_code=status_code,
        )

    if error or not code:
        return page("Verbindung abgebrochen", "Strava wurde nicht verbunden. Du kannst das Fenster schliessen.", 400)
    user_id = read_state_token(state, "strava")
    if user_id is None:
        return page("Link abgelaufen", "Bitte starte die Verbindung in der App erneut.", 400)
    try:
        strava.exchange_code(db, user_id, code)
    except strava.StravaError as e:
        return page("Fehler", str(e), 502)
    return page("Strava verbunden", "Du kannst dieses Fenster schliessen und zur App zurueckkehren.")


@router.post("/integrations/strava/sync")
def sync(full: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = _require_connected(db, user)
    try:
        return strava.sync_activities(db, integ, user.profile, full=full)
    except strava.StravaError as e:
        raise HTTPException(e.status if e.status in (401, 429) else 502, str(e))


@router.delete("/integrations/strava", status_code=204)
def disconnect(user: User = Depends(current_user), db: Session = Depends(get_db)):
    integ = _require_connected(db, user)
    strava.StravaClient(db, integ).deauthorize()
    db.delete(integ)
    db.commit()


@router.post("/integrations/strava/subscribe")
def subscribe(user: User = Depends(current_user)):
    """Registriert den Webhook bei Strava (einmalig; PUBLIC_BASE_URL muss oeffentlich erreichbar sein)."""
    s = get_settings()
    r = httpx.post(
        "https://www.strava.com/api/v3/push_subscriptions",
        data={
            "client_id": s.strava_client_id,
            "client_secret": s.strava_client_secret,
            "callback_url": f"{s.public_base_url.rstrip('/')}/webhooks/strava",
            "verify_token": s.strava_verify_token,
        },
        timeout=30,
    )
    if r.status_code >= 300:
        raise HTTPException(502, f"Strava lehnte die Webhook-Registrierung ab: {r.text[:200]}")
    return r.json()


@router.get("/webhooks/strava")
def webhook_verify(
    mode: str = Query("", alias="hub.mode"),
    challenge: str = Query("", alias="hub.challenge"),
    verify_token: str = Query("", alias="hub.verify_token"),
):
    if mode != "subscribe" or verify_token != get_settings().strava_verify_token:
        raise HTTPException(403, "Ungueltiges Verify-Token")
    return {"hub.challenge": challenge}


@router.post("/webhooks/strava")
async def webhook_event(request: Request, db: Session = Depends(get_db)):
    event = await request.json()
    try:
        result = strava.handle_webhook_event(db, event)
    except strava.StravaError:
        result = "error"  # Strava erwartet trotzdem 200, sonst wiederholt es den Aufruf
    return PlainTextResponse(result)
