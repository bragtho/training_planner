"""Wissensbasis: Verwaltungs-Schnittstelle fuer den Wissens-Manager (Schluessel) und lesender Zugriff fuer die App."""

import secrets
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import knowledge as K
from ..config import get_settings
from ..db import get_db
from ..models import KnowledgeCandidate, KnowledgeCard, KnowledgeHistory, KnowledgeSource, User
from ..security import current_user

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    token = get_settings().knowledge_admin_token
    if not token:
        raise HTTPException(503, "Die Verwaltungs-Schnittstelle ist gesperrt: KNOWLEDGE_ADMIN_TOKEN fehlt in backend/.env")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, token):
        raise HTTPException(401, "Ungueltiger Verwaltungsschluessel")


admin = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def _bad(e: K.KnowledgeError) -> HTTPException:
    return HTTPException(404 if "nicht gefunden" in str(e) else 422, str(e))


def _card(db: Session, slug: str) -> KnowledgeCard:
    card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.slug == slug))
    if card is None:
        raise HTTPException(404, "Karte nicht gefunden")
    return card


@admin.get("/known")
def known(db: Session = Depends(get_db)):
    """Alle bekannten DOIs und PMIDs, damit der Manager nichts doppelt vorschlaegt."""
    return K.known_identifiers(db)


@admin.post("/candidates")
def post_candidates(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        return K.ingest_candidates(db, body.get("items"))
    except K.KnowledgeError as e:
        raise _bad(e)


@admin.get("/candidates")
def list_candidates(status: str | None = None, db: Session = Depends(get_db)):
    if status is not None and status not in K.CANDIDATE_STATUSES:
        raise HTTPException(422, f"status muss eines von {', '.join(K.CANDIDATE_STATUSES)} sein")
    q = select(KnowledgeCandidate).order_by(KnowledgeCandidate.id)
    if status:
        q = q.where(KnowledgeCandidate.status == status)
    return [K.candidate_view(c) for c in db.scalars(q)]


@admin.post("/candidates/{candidate_id}/decide")
def decide(candidate_id: int, body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        return K.decide_candidate(db, candidate_id, body.get("action"), body.get("note"), body.get("card"), body.get("sources"))
    except K.KnowledgeError as e:
        raise _bad(e)


@admin.get("/cards")
def list_cards(status: str | None = None, db: Session = Depends(get_db)):
    q = select(KnowledgeCard).order_by(KnowledgeCard.topic, KnowledgeCard.slug)
    if status:
        q = q.where(KnowledgeCard.status == status)
    return [K.card_view(db, c) for c in db.scalars(q)]


@admin.get("/cards/{slug}")
def get_card(slug: str, db: Session = Depends(get_db)):
    return K.card_view(db, _card(db, slug))


@admin.put("/cards/{slug}")
def put_card(slug: str, body: dict = Body(...), db: Session = Depends(get_db)):
    """Karte anlegen oder aendern; optional mit den benoetigten Quellen (body.sources)."""
    data: dict[str, Any] = {**body, "slug": slug}
    try:
        for s in body.get("sources") or []:
            K.save_source(db, s)
        card = K.save_card(db, data, note=body.get("note"))
    except K.KnowledgeError as e:
        db.rollback()
        raise _bad(e)
    return K.card_view(db, card)


@admin.post("/cards/{slug}/retire")
def retire(slug: str, body: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        return K.card_view(db, K.retire_card(db, slug, body.get("note")))
    except K.KnowledgeError as e:
        raise _bad(e)


@admin.get("/cards/{slug}/history")
def history(slug: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(KnowledgeHistory).where(KnowledgeHistory.card_slug == slug).order_by(KnowledgeHistory.id.desc()))
    return [{"version": h.version, "action": h.action, "note": h.note, "changed_at": h.changed_at.isoformat(), "snapshot": h.snapshot}
            for h in rows]


@admin.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    return [K.source_view(s) for s in db.scalars(select(KnowledgeSource).order_by(KnowledgeSource.key))]


@admin.put("/sources/{key}")
def put_source(key: str, body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        src = K.save_source(db, {**body, "key": key})
        db.commit()
    except K.KnowledgeError as e:
        db.rollback()
        raise _bad(e)
    return K.source_view(src)


@admin.get("/export")
def export(db: Session = Depends(get_db)):
    """Vollstaendige Sicherung (Quellen, Karten, Kandidaten, Verlauf) als JSON."""
    return K.export_all(db)


router.include_router(admin)


@router.get("/cards/{slug}")
def read_card(slug: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Karte fuer die App (Quellen-Chips): nur aktive oder umstrittene Karten."""
    card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.slug == slug, KnowledgeCard.status.in_(K.ACTIVE_STATUSES)))
    if card is None:
        raise HTTPException(404, "Karte nicht gefunden")
    view = K.card_view(db, card)
    view.pop("claims", None)  # die Belegzitate dienen der Pruefung, die App zeigt Empfehlung, Grenzen und Quellen
    return view
