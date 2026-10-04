"""Wissensbasis des Coaches: geprueft erfasste Studien (Quellen) und daraus abgeleitete Wissenskarten.

Die Pruefregeln sitzen hier und nicht im Wissens-Manager, damit sie nur einmal existieren: Der Manager
liefert Entwuerfe, das Backend entscheidet, was als Karte gespeichert werden darf. Der Coach liest nur
aktive Karten (active, contested); Entwuerfe, Watchlist und stillgelegte Karten sind fuer ihn unsichtbar.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KnowledgeCandidate, KnowledgeCard, KnowledgeHistory, KnowledgeSource

TOPICS = {
    "intervalle": "Intervalle",
    "zonen": "Zonenmodelle und Tests",
    "periodisierung": "Training und Periodisierung",
    "tapering": "Tapering und Wettkampf",
    "ernaehrung": "Ernährung und Energie",
    "kraft": "Kraft",
    "hitze": "Hitze",
    "hoehe": "Höhe",
    "frauen": "Frauen",
    "masters": "Masters",
    "erholung": "Erholung und Monitoring",
    "sonstiges": "Sonstiges",
}
EVIDENCE = {"A": "starke Evidenz", "B": "moderate Evidenz", "C": "schwache Evidenz", "D": "Expertenpraxis"}
DIRECTNESS = {"direct": "direkt übertragbar", "indirect": "indirekt (andere Population)", "extrapolated": "extrapoliert"}
STATUSES = ("active", "contested", "watch", "retired")
ACTIVE_STATUSES = ("active", "contested")  # nur diese sieht der Coach
DESIGNS = {
    "systematic_review": "Systematic Review",
    "meta_analysis": "Metaanalyse",
    "consensus": "Konsens-Statement",
    "guideline": "Leitlinie",
    "rct": "RCT",
    "crossover_trial": "Crossover-Studie",
    "cohort": "Kohortenstudie",
    "observational": "Beobachtungsstudie",
    "review": "Übersichtsarbeit",
    "expert": "Expertenmeinung",
    "other": "Sonstige",
}
STRONG_DESIGNS = {"systematic_review", "meta_analysis", "consensus", "guideline"}
TRIAL_DESIGNS = {"rct", "crossover_trial"}
CONSENSUS_DESIGNS = {"consensus", "guideline"}
CANDIDATE_STATUSES = ("pending", "accepted", "rejected", "watch")
POPULATIONS = {"elite", "trained", "recreational"}
SEXES = {"all", "female", "male"}
REVIEW_MONTHS = 12
QUOTE_MAX_WORDS = 25
MAX_CARDS = 300

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{2,59}$")
_DOI = re.compile(r"^10\.\d{4,9}/\S+$")


class KnowledgeError(ValueError):
    """Ungueltige Eingabe; die Meldung ist fuer den Nutzer des Wissens-Managers gedacht."""


def _text(v: Any, name: str, max_len: int, required: bool = True) -> str | None:
    s = " ".join(str(v or "").split())
    if not s:
        if required:
            raise KnowledgeError(f"{name} fehlt")
        return None
    if len(s) > max_len:
        raise KnowledgeError(f"{name} ist laenger als {max_len} Zeichen")
    return s


def _long_text(v: Any, name: str, max_len: int, required: bool = True) -> str | None:
    s = "\n".join(line.strip() for line in str(v or "").strip().splitlines()).strip()
    if not s:
        if required:
            raise KnowledgeError(f"{name} fehlt")
        return None
    if len(s) > max_len:
        raise KnowledgeError(f"{name} ist laenger als {max_len} Zeichen")
    return s


def _date(v: Any, name: str) -> dt.date:
    try:
        return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise KnowledgeError(f"{name}: '{v}' ist kein Datum (YYYY-MM-DD)")


def normalize_doi(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s or None


def normalize_pmid(v: Any) -> str | None:
    s = re.sub(r"\D", "", str(v or ""))
    return s or None


# ----------------------------------------------------------------- Quellen ---


def save_source(db: Session, data: dict) -> KnowledgeSource:
    """Legt eine Quelle an oder aktualisiert sie (Schluessel ist eindeutig)."""
    if not isinstance(data, dict):
        raise KnowledgeError("Quelle muss ein Objekt sein")
    key = str(data.get("key") or "").strip()
    if not _KEY.match(key):
        raise KnowledgeError("key: nur Kleinbuchstaben, Ziffern und Bindestriche, 3-60 Zeichen (z. B. seiler-2010)")
    year = data.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= dt.date.today().year + 1:
        raise KnowledgeError("year muss eine Jahreszahl sein")
    design = data.get("design")
    if design not in DESIGNS:
        raise KnowledgeError(f"design muss eines von {', '.join(DESIGNS)} sein")
    basis = data.get("basis", "abstract")
    if basis not in ("fulltext", "abstract"):
        raise KnowledgeError("basis muss fulltext oder abstract sein")
    doi = normalize_doi(data.get("doi"))
    if doi and not _DOI.match(doi):
        raise KnowledgeError(f"doi '{doi}' hat kein gueltiges Format")
    n = data.get("sample_n")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 0):
        raise KnowledgeError("sample_n muss eine nichtnegative ganze Zahl sein")
    src = db.scalar(select(KnowledgeSource).where(KnowledgeSource.key == key)) or KnowledgeSource(key=key)
    src.authors = _text(data.get("authors"), "authors", 300)
    src.year = year
    src.title = _text(data.get("title"), "title", 500)
    src.journal = _text(data.get("journal"), "journal", 200, required=False)
    src.doi = doi
    src.pmid = normalize_pmid(data.get("pmid"))
    src.design = design
    src.sample_n = n
    src.population = _text(data.get("population"), "population", 200, required=False)
    src.basis = basis
    src.retracted = bool(data.get("retracted", False))
    src.retraction_checked = _date(data["retraction_checked"], "retraction_checked") if data.get("retraction_checked") else None
    db.add(src)
    db.flush()
    return src


def citation(src: KnowledgeSource) -> str:
    """Kurzbeleg wie "Seiler 2010" oder "Seiler et al. 2010"."""
    entries = [a.strip() for a in src.authors.split(",") if a.strip()]
    tokens = entries[0].split() if entries else []
    if len(tokens) > 1 and tokens[-1].isupper() and len(tokens[-1]) <= 3:
        tokens = tokens[:-1]  # Initialen entfernen
    family = " ".join(tokens) or src.authors
    return f"{family}{' et al.' if len(entries) > 1 else ''} {src.year}"


def source_view(src: KnowledgeSource) -> dict:
    return {
        "key": src.key, "citation": citation(src), "authors": src.authors, "year": src.year, "title": src.title,
        "journal": src.journal, "doi": src.doi, "pmid": src.pmid, "design": src.design, "design_label": DESIGNS[src.design],
        "sample_n": src.sample_n, "population": src.population, "basis": src.basis, "retracted": src.retracted,
        "retraction_checked": src.retraction_checked.isoformat() if src.retraction_checked else None,
        "url": f"https://doi.org/{src.doi}" if src.doi else (f"https://pubmed.ncbi.nlm.nih.gov/{src.pmid}/" if src.pmid else None),
    }


# ------------------------------------------------------------------ Karten ---


def _sources_by_key(db: Session, keys: set[str]) -> dict[str, KnowledgeSource]:
    if not keys:
        return {}
    return {s.key: s for s in db.scalars(select(KnowledgeSource).where(KnowledgeSource.key.in_(keys)))}


def validate_card(db: Session, data: dict, today: dt.date | None = None) -> dict:
    """Prueft einen Kartenentwurf gegen alle Regeln und gibt bereinigte Felder zurueck."""
    today = today or dt.date.today()
    if not isinstance(data, dict):
        raise KnowledgeError("Karte muss ein Objekt sein")
    slug = str(data.get("slug") or "").strip()
    if not _SLUG.match(slug):
        raise KnowledgeError("slug: nur Kleinbuchstaben, Ziffern und Bindestriche, 3-80 Zeichen (z. B. vo2max-4x4)")
    topic = data.get("topic")
    if topic not in TOPICS:
        raise KnowledgeError(f"topic muss eines von {', '.join(TOPICS)} sein")
    evidence = data.get("evidence")
    if evidence not in EVIDENCE:
        raise KnowledgeError("evidence muss A, B, C oder D sein")
    directness = data.get("directness")
    if directness not in DIRECTNESS:
        raise KnowledgeError(f"directness muss eines von {', '.join(DIRECTNESS)} sein")
    status = data.get("status", "active")
    if status not in STATUSES:
        raise KnowledgeError(f"status muss eines von {', '.join(STATUSES)} sein")

    tags = data.get("tags") or []
    if not isinstance(tags, list) or len(tags) > 12 or any(not isinstance(t, str) or not t.strip() or len(t) > 40 for t in tags):
        raise KnowledgeError("tags muss eine Liste mit hoechstens 12 kurzen Woertern sein")
    applies = data.get("applies_to") or {}
    if not isinstance(applies, dict):
        raise KnowledgeError("applies_to muss ein Objekt sein")
    pops = applies.get("population") or []
    if not isinstance(pops, list) or not set(pops) <= POPULATIONS:
        raise KnowledgeError(f"applies_to.population darf nur {', '.join(sorted(POPULATIONS))} enthalten")
    sex = applies.get("sex", "all")
    if sex not in SEXES:
        raise KnowledgeError("applies_to.sex muss all, female oder male sein")
    applies_clean = {"population": sorted(pops), "sex": sex, "age": _text(applies.get("age"), "applies_to.age", 40, required=False)}

    claims_in = data.get("claims") or []
    if not isinstance(claims_in, list):
        raise KnowledgeError("claims muss eine Liste sein")
    claims: list[dict] = []
    for i, c in enumerate(claims_in):
        pre = f"claims[{i}]"
        if not isinstance(c, dict):
            raise KnowledgeError(f"{pre} muss ein Objekt sein")
        quote = _text(c.get("quote"), f"{pre}.quote", 400)
        if len(quote.split()) > QUOTE_MAX_WORDS:
            raise KnowledgeError(f"{pre}.quote hat mehr als {QUOTE_MAX_WORDS} Woerter (nur kurze woertliche Belegzitate)")
        claims.append({"text": _text(c.get("text"), f"{pre}.text", 300), "quote": quote,
                       "source_key": str(c.get("source_key") or "").strip()})

    positions = data.get("positions")
    positions_clean = None
    if status == "contested":
        if not isinstance(positions, list) or len(positions) < 2:
            raise KnowledgeError("Eine umstrittene Karte braucht mindestens zwei Positionen (positions)")
        positions_clean = []
        for i, p in enumerate(positions):
            if not isinstance(p, dict):
                raise KnowledgeError(f"positions[{i}] muss ein Objekt sein")
            keys = p.get("source_keys") or []
            if not isinstance(keys, list) or not keys:
                raise KnowledgeError(f"positions[{i}] braucht source_keys mit mindestens einer Quelle")
            positions_clean.append({"label": _text(p.get("label"), f"positions[{i}].label", 120),
                                    "summary": _text(p.get("summary"), f"positions[{i}].summary", 400),
                                    "source_keys": [str(k) for k in keys]})

    all_keys = {c["source_key"] for c in claims} | {k for p in (positions_clean or []) for k in p["source_keys"]}
    sources = _sources_by_key(db, all_keys)
    missing = sorted(all_keys - set(sources))
    if missing:
        raise KnowledgeError(f"Unbekannte Quelle(n): {', '.join(missing)} (zuerst als Quelle anlegen)")
    retracted = sorted(k for k, s in sources.items() if s.retracted)
    if retracted:
        raise KnowledgeError(f"Zurückgezogene Quelle(n) dürfen nicht belegen: {', '.join(retracted)}")

    claim_sources = [sources[c["source_key"]] for c in claims]
    if evidence in ("A", "B", "C") and not claims:
        raise KnowledgeError("Evidenz A-C braucht mindestens eine belegte Aussage (claims mit Zitat und Quelle)")
    if evidence in ("A", "B", "C") and claim_sources and all(s.design == "expert" for s in claim_sources):
        raise KnowledgeError("Expertenmeinung allein belegt nur Stufe D")
    if evidence == "A":
        if not any(s.design in STRONG_DESIGNS and s.basis == "fulltext" for s in claim_sources):
            raise KnowledgeError("Stufe A braucht eine Systematic Review, Metaanalyse oder ein Konsens-Statement mit Volltext als Quelle")
    elif evidence == "B":
        if not any(s.design in STRONG_DESIGNS | TRIAL_DESIGNS for s in claim_sources):
            raise KnowledgeError("Stufe B braucht mindestens eine randomisierte Studie, Review oder ein Konsens-Statement als Quelle")
    safety = bool(data.get("safety", False))
    if safety and not (evidence == "A" and any(s.design in CONSENSUS_DESIGNS for s in claim_sources)):
        raise KnowledgeError("Sicherheitsrelevante Karten (safety) brauchen Stufe A mit Konsens-Statement oder Leitlinie als Quelle")

    reviewed = _date(data["reviewed"], "reviewed") if data.get("reviewed") else today
    review_due = _date(data["review_due"], "review_due") if data.get("review_due") else _add_months(reviewed, REVIEW_MONTHS)
    if review_due < reviewed:
        raise KnowledgeError("review_due liegt vor reviewed")

    return {
        "slug": slug, "title": _text(data.get("title"), "title", 200), "topic": topic,
        "tags": sorted({t.strip().lower() for t in tags}), "summary": _long_text(data.get("summary"), "summary", 400),
        "recommendation": _long_text(data.get("recommendation"), "recommendation", 800),
        "evidence": evidence, "directness": directness, "applies_to": applies_clean,
        "caveats": _long_text(data.get("caveats"), "caveats", 800, required=False), "status": status,
        "positions": positions_clean, "safety": safety, "claims": claims, "reviewed": reviewed, "review_due": review_due,
    }


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


def card_snapshot(card: KnowledgeCard) -> dict:
    return {
        "slug": card.slug, "title": card.title, "topic": card.topic, "tags": card.tags, "summary": card.summary,
        "recommendation": card.recommendation, "evidence": card.evidence, "directness": card.directness,
        "applies_to": card.applies_to, "caveats": card.caveats, "status": card.status, "positions": card.positions,
        "safety": card.safety, "claims": card.claims, "reviewed": card.reviewed.isoformat(),
        "review_due": card.review_due.isoformat(), "version": card.version,
    }


def save_card(db: Session, data: dict, note: str | None = None, today: dt.date | None = None) -> KnowledgeCard:
    """Legt eine Karte an oder aktualisiert sie (neue Version, Verlauf)."""
    clean = validate_card(db, data, today)
    card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.slug == clean["slug"]))
    if card is None:
        if db.query(KnowledgeCard).count() >= MAX_CARDS:
            raise KnowledgeError(f"Höchstens {MAX_CARDS} Karten")
        card = KnowledgeCard(version=1, **clean)
        db.add(card)
        action = "created"
    else:
        for k, v in clean.items():
            setattr(card, k, v)
        card.version += 1
        action = "retired" if card.status == "retired" else "updated"
    db.flush()
    db.add(KnowledgeHistory(card_slug=card.slug, version=card.version, action=action, snapshot=card_snapshot(card),
                            note=_text(note, "note", 300, required=False)))
    db.commit()
    return card


def retire_card(db: Session, slug: str, note: str | None = None) -> KnowledgeCard:
    card = db.scalar(select(KnowledgeCard).where(KnowledgeCard.slug == slug))
    if card is None:
        raise KnowledgeError("Karte nicht gefunden")
    card.status = "retired"
    card.version += 1
    db.add(KnowledgeHistory(card_slug=slug, version=card.version, action="retired", snapshot=card_snapshot(card),
                            note=_text(note, "note", 300, required=False)))
    db.commit()
    return card


def card_sources(db: Session, card: KnowledgeCard) -> list[KnowledgeSource]:
    keys = {c["source_key"] for c in (card.claims or [])} | {k for p in (card.positions or []) for k in p["source_keys"]}
    return sorted(_sources_by_key(db, keys).values(), key=lambda s: (-s.year, s.key))


def card_view(db: Session, card: KnowledgeCard, today: dt.date | None = None) -> dict:
    """Vollansicht einer Karte fuer Coach-Werkzeug, App und Verwaltung; Beschriftungen kommen aus den Feldern."""
    today = today or dt.date.today()
    srcs = {s.key: s for s in card_sources(db, card)}
    return {
        "slug": card.slug, "title": card.title, "topic": card.topic, "topic_label": TOPICS[card.topic], "tags": card.tags,
        "summary": card.summary, "recommendation": card.recommendation,
        "evidence": card.evidence, "evidence_label": EVIDENCE[card.evidence],
        "practice": card.evidence in ("C", "D"),  # schwache Evidenz oder Praxiswissen: so kennzeichnen
        "directness": card.directness, "directness_label": DIRECTNESS[card.directness],
        "applies_to": card.applies_to, "caveats": card.caveats, "status": card.status, "contested": card.status == "contested",
        "positions": card.positions, "safety": card.safety, "version": card.version,
        "reviewed": card.reviewed.isoformat(), "review_due": card.review_due.isoformat(), "review_overdue": card.review_due < today,
        "claims": [{"text": c["text"], "quote": c["quote"], "citation": citation(srcs[c["source_key"]]), "source_key": c["source_key"]}
                   for c in card.claims if c["source_key"] in srcs],
        "sources": [source_view(s) for s in srcs.values()],
    }


def chip_view(card: KnowledgeCard, tagged: bool) -> dict:
    """Kurzform fuer die Quellen-Chips unter einer Coach-Antwort (vom Backend, nicht vom Modell formuliert)."""
    return {
        "slug": card.slug, "title": card.title, "evidence": card.evidence, "evidence_label": EVIDENCE[card.evidence],
        "directness": card.directness, "directness_label": DIRECTNESS[card.directness],
        "practice": card.evidence in ("C", "D"), "contested": card.status == "contested", "safety": card.safety, "tagged": tagged,
    }


def active_cards(db: Session) -> list[KnowledgeCard]:
    """Karten, die der Coach nutzen darf, nach Thema und Slug sortiert."""
    return list(db.scalars(select(KnowledgeCard).where(KnowledgeCard.status.in_(ACTIVE_STATUSES)).order_by(KnowledgeCard.topic, KnowledgeCard.slug)))


def index_lines(db: Session) -> list[str]:
    """Titel-Index fuer den (gecachten) Systemprompt: eine Zeile je aktiver Karte."""
    return [f"- {c.slug} | {c.title} | {TOPICS[c.topic]} | Evidenz {c.evidence}{' | umstritten' if c.status == 'contested' else ''}"
            for c in active_cards(db)]


def cards_for_tool(db: Session, ids: list[str] | None, topic: str | None, limit: int = 6) -> dict:
    """Ergebnis des Coach-Werkzeugs get_knowledge: Karten nach IDs oder Thema, plus unbekannte IDs."""
    cards = {c.slug: c for c in active_cards(db)}
    chosen: list[KnowledgeCard] = []
    unknown: list[str] = []
    for slug in ids or []:
        slug = str(slug).strip()
        if slug in cards:
            chosen.append(cards[slug])
        else:
            unknown.append(slug)
    if topic:
        chosen += [c for c in cards.values() if c.topic == topic and c not in chosen]
    out = {"cards": [card_view(db, c) for c in chosen[:limit]], "unknown_ids": unknown}
    if len(chosen) > limit:
        out["note"] = f"Nur die ersten {limit} von {len(chosen)} Karten, frage gezielter mit ids"
    if not chosen:
        out["hint"] = "Keine passende Karte: Kennzeichne Aussagen als Praxiswissen ohne geprüfte Quelle und erfinde keine Belege."
    return out


# -------------------------------------------------------- Zitat-Integritaet ---

_TAG = re.compile(r"\s?\[\[\s*kb:\s*([^\]]*?)\s*\]\]")


def process_citations(text: str, known_slugs: set[str]) -> tuple[str, list[str]]:
    """Entfernt [[kb:slug]]-Markierungen aus dem Text und gibt die gueltigen, getaggten Slugs zurueck.

    Unbekannte Slugs verschwinden ersatzlos: Angezeigt wird nur, was es in der Wissensbasis wirklich gibt.
    """
    tagged: list[str] = []
    for m in _TAG.finditer(text):
        for slug in re.split(r"[,\s]+", m.group(1)):
            if slug in known_slugs and slug not in tagged:
                tagged.append(slug)
    cleaned = _TAG.sub("", text)
    cleaned = re.sub(r"[ \t]+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip(), tagged


# ------------------------------------------------------------- Kandidaten ---


def known_identifiers(db: Session) -> dict:
    """Alle bekannten DOIs/PMIDs (Quellen und Kandidaten jeden Status), damit der Manager nichts doppelt vorschlaegt."""
    dois = {s.doi for s in db.scalars(select(KnowledgeSource)) if s.doi} | {c.doi for c in db.scalars(select(KnowledgeCandidate)) if c.doi}
    pmids = {s.pmid for s in db.scalars(select(KnowledgeSource)) if s.pmid} | {c.pmid for c in db.scalars(select(KnowledgeCandidate)) if c.pmid}
    return {"dois": sorted(dois), "pmids": sorted(pmids)}


def ingest_candidates(db: Session, items: Any) -> dict:
    if not isinstance(items, list) or not items:
        raise KnowledgeError("items muss eine nichtleere Liste sein")
    if len(items) > 100:
        raise KnowledgeError("Hoechstens 100 Kandidaten je Aufruf")
    known = known_identifiers(db)
    seen_d, seen_p = set(known["dois"]), set(known["pmids"])
    created = skipped = 0
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise KnowledgeError(f"items[{i}] muss ein Objekt sein")
        doi, pmid = normalize_doi(it.get("doi")), normalize_pmid(it.get("pmid"))
        title = _text(it.get("title"), f"items[{i}].title", 500)
        topic = it.get("topic")
        if topic not in TOPICS:
            raise KnowledgeError(f"items[{i}].topic muss eines von {', '.join(TOPICS)} sein")
        analysis = it.get("analysis") or {}
        if not isinstance(analysis, dict):
            raise KnowledgeError(f"items[{i}].analysis muss ein Objekt sein")
        if (doi and doi in seen_d) or (pmid and pmid in seen_p):
            skipped += 1
            continue
        db.add(KnowledgeCandidate(doi=doi, pmid=pmid, title=title, topic=topic, analysis=analysis))
        seen_d |= {doi} if doi else set()
        seen_p |= {pmid} if pmid else set()
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


def candidate_view(c: KnowledgeCandidate) -> dict:
    return {"id": c.id, "doi": c.doi, "pmid": c.pmid, "title": c.title, "topic": c.topic, "status": c.status, "analysis": c.analysis,
            "decision_note": c.decision_note, "created_at": c.created_at.isoformat(),
            "decided_at": c.decided_at.isoformat() if c.decided_at else None}


def decide_candidate(db: Session, candidate_id: int, action: str, note: str | None = None,
                     card: dict | None = None, sources: list[dict] | None = None) -> dict:
    """Entscheidung des Nutzers: accept (mit Kartenentwurf und Quellen), watch oder reject."""
    cand = db.get(KnowledgeCandidate, candidate_id)
    if cand is None:
        raise KnowledgeError("Kandidat nicht gefunden")
    if cand.status != "pending":
        raise KnowledgeError(f"Kandidat ist schon entschieden ({cand.status})")
    result: dict = {}
    if action == "accept":
        if not isinstance(card, dict):
            raise KnowledgeError("Zum Aufnehmen gehört ein Kartenentwurf (card)")
        try:
            for s in sources or []:
                save_source(db, s)
            saved = save_card(db, card, note=note)
        except KnowledgeError:
            db.rollback()
            raise
        result["card"] = card_view(db, saved)
        cand.status = "accepted"
    elif action in ("reject", "watch"):
        if action == "reject" and not _text(note, "note", 500, required=False):
            raise KnowledgeError("Beim Verwerfen bitte einen kurzen Grund angeben")
        cand.status = "rejected" if action == "reject" else "watch"
    else:
        raise KnowledgeError("action muss accept, watch oder reject sein")
    cand.decision_note = _text(note, "note", 500, required=False)
    cand.decided_at = dt.datetime.now(dt.timezone.utc)
    db.commit()
    result["candidate"] = candidate_view(cand)
    return result


def export_all(db: Session) -> dict:
    """Vollstaendige Sicherung der Wissensbasis als JSON-faehiges Objekt."""
    return {
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sources": [source_view(s) for s in db.scalars(select(KnowledgeSource).order_by(KnowledgeSource.key))],
        "cards": [card_snapshot(c) for c in db.scalars(select(KnowledgeCard).order_by(KnowledgeCard.slug))],
        "candidates": [candidate_view(c) for c in db.scalars(select(KnowledgeCandidate).order_by(KnowledgeCandidate.id))],
        "history": [{"card_slug": h.card_slug, "version": h.version, "action": h.action, "note": h.note,
                     "changed_at": h.changed_at.isoformat()} for h in db.scalars(select(KnowledgeHistory).order_by(KnowledgeHistory.id))],
    }
