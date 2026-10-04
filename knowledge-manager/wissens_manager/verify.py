"""Deterministische Pruefungen ohne KI: Belegzitate im Abstract finden, Rueckzug erkennen, Quellenschluessel bilden."""

from __future__ import annotations

import re
import unicodedata

import httpx

from .europepmc import USER_AGENT, Paper

CROSSREF = "https://api.crossref.org/works"
_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"',
                         "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-", "­": None, " ": " "})


_TRANSLIT = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L"})


def normalize_text(s: str) -> str:
    """Vergleichsform: Unicode normalisiert, typografische Zeichen vereinheitlicht, Gross/Klein und Leerraum egal."""
    s = unicodedata.normalize("NFKC", s or "").translate(_QUOTES).casefold()
    return " ".join(s.split())


def quote_found(quote: str, text: str) -> bool:
    q = normalize_text(quote).strip(" .…")
    return bool(q) and q in normalize_text(text)


def check_quotes(quotes: list[str], text: str) -> list[dict]:
    return [{"quote": q, "found": quote_found(q, text)} for q in quotes]


def crossref_work(doi: str, *, http: httpx.Client | None = None) -> dict | None:
    """Metadaten einer DOI bei Crossref; None, wenn unbekannt oder nicht erreichbar."""
    client = http or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT})
    try:
        resp = client.get(f"{CROSSREF}/{doi}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("message")
    except (httpx.HTTPError, ValueError):
        return None


def retraction_status(paper: Paper, crossref: dict | None) -> dict:
    """ok | retracted | unknown. Quellen: Europe-PMC-Studientyp und Crossref-Aktualisierungen (retraction, withdrawal, removal)."""
    if paper.retracted_flag:
        return {"status": "retracted", "reason": "Europe PMC: als zurückgezogen gekennzeichnet"}
    if crossref is None:
        return {"status": "unknown", "reason": "Crossref nicht erreichbar oder DOI unbekannt"}
    for u in (crossref.get("updated-by") or []):
        if str(u.get("type", "")).lower() in {"retraction", "withdrawal", "removal"}:
            return {"status": "retracted", "reason": f"Crossref: {u.get('type')} ({u.get('DOI', '')})"}
    return {"status": "ok", "reason": "Kein Rückzug bei Europe PMC und Crossref gefunden"}


def metadata_matches(paper: Paper, crossref: dict | None) -> bool | None:
    """Stimmen Titel und Jahr mit Crossref ueberein? None, wenn Crossref nichts liefert."""
    if not crossref:
        return None
    titles = crossref.get("title") or []
    # Nur Buchstaben und Ziffern vergleichen; ein Titel darf der Anfang des anderen sein (Untertitel, Satzzeichen, Gross/Klein egal)
    a = re.sub(r"[^a-z0-9]", "", normalize_text(titles[0] if titles else ""))[:80]
    b = re.sub(r"[^a-z0-9]", "", normalize_text(paper.title))[:80]
    title_ok = bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))
    parts = ((crossref.get("issued") or {}).get("date-parts") or [[None]])[0]
    year_ok = paper.year is None or parts[0] is None or abs(int(parts[0]) - paper.year) <= 1
    return title_ok and year_ok


def source_key(paper: Paper, taken: set[str]) -> str:
    """Schluessel wie "seiler-2010"; bei Kollision mit a, b, ... ergaenzt."""
    first = (paper.authors.split(",")[0] if paper.authors else "studie").split()
    family = next((t for t in first if len(t) > 2 and not t.isupper()), first[0] if first else "studie")
    family = family.translate(_TRANSLIT)  # Buchstaben ohne Zerlegung (o mit Strich u. a.) sonst verschluckt
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", family).encode("ascii", "ignore").decode().lower()).strip("-") or "studie"
    base = f"{base}-{paper.year or 'xxxx'}"
    key, i = base, 0
    while key in taken:
        i += 1
        key = f"{base}{chr(96 + i)}" if i <= 26 else f"{base}-{i}"
    return key
