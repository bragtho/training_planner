"""Europe PMC (REST): Studien suchen und Abstracts holen. Kostenlos, ohne Schluessel."""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field

import httpx

BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
USER_AGENT = "Wissens-Manager/0.1 (Recherche fuer eine Radtrainings-App)"


@dataclass
class Paper:
    title: str
    abstract: str
    year: int | None = None
    journal: str | None = None
    authors: str = ""
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    pub_types: list[str] = field(default_factory=list)
    open_access: bool = False
    cited_by: int = 0

    @property
    def retracted_flag(self) -> bool:
        return any("retract" in t.lower() for t in self.pub_types)

    @property
    def url(self) -> str | None:
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/" if self.pmid else None

    def to_dict(self) -> dict:
        return asdict(self) | {"url": self.url}


def clean_abstract(raw: str | None) -> str:
    """Entfernt HTML-Auszeichnung aus dem Abstract (Europe PMC liefert z. B. <h4>Background</h4>) und normalisiert Leerraum."""
    text = re.sub(r"</?(h\d|p|br|b|i|sup|sub|strong|em|abstract|sec|title|label)[^>]*>", " ", raw or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(html.unescape(text).split())


def parse_result(r: dict) -> Paper:
    types = (r.get("pubTypeList") or {}).get("pubType") or []
    journal = r.get("journalTitle") or (((r.get("journalInfo") or {}).get("journal") or {}).get("title"))
    year = r.get("pubYear")
    return Paper(
        title=clean_abstract(r.get("title")).rstrip("."),
        abstract=clean_abstract(r.get("abstractText")),
        year=int(year) if str(year or "").isdigit() else None,
        journal=journal,
        authors=r.get("authorString") or "",
        doi=(r.get("doi") or "").lower() or None,
        pmid=r.get("pmid") or (r.get("id") if r.get("source") == "MED" else None),
        pmcid=r.get("pmcid"),
        pub_types=[t for t in types if isinstance(t, str)],
        open_access=r.get("isOpenAccess") == "Y",
        cited_by=int(r.get("citedByCount") or 0),
    )


def _client(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT})


def search(query: str, *, limit: int = 25, http: httpx.Client | None = None, skip=lambda p: False) -> list[Paper]:
    """Sucht Studien und gibt hoechstens `limit` Treffer mit Abstract zurueck, die `skip` nicht aussortiert.

    Blaettert mit cursorMark, bis genug Treffer da sind (hoechstens 6 Seiten), damit bereits bekannte Studien
    die Ausbeute nicht auffressen.
    """
    client = _client(http)
    out: list[Paper] = []
    seen: set[str] = set()
    cursor = "*"
    for _ in range(6):
        resp = client.get(f"{BASE}/search", params={"query": query, "format": "json", "resultType": "core",
                                                    "pageSize": 50, "cursorMark": cursor, "sort": "CITED desc"})
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("resultList", {}).get("result", []):
            paper = parse_result(r)
            key = paper.doi or paper.pmid or paper.title
            if key in seen or not paper.abstract or paper.retracted_flag or skip(paper):
                continue
            seen.add(key)
            out.append(paper)
            if len(out) >= limit:
                return out
        nxt = data.get("nextCursorMark")
        if not nxt or nxt == cursor or not data.get("resultList", {}).get("result"):
            break
        cursor = nxt
    return out


def fetch(identifier: str, *, http: httpx.Client | None = None) -> Paper | None:
    """Holt eine einzelne Studie per DOI oder PMID."""
    ident = identifier.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if ident.lower().startswith(prefix):
            ident = ident[len(prefix):]
    digits = re.sub(r"\D", "", ident)
    query = f'DOI:"{ident}"' if "/" in ident else f"EXT_ID:{digits} AND SRC:MED"
    resp = _client(http).get(f"{BASE}/search", params={"query": query, "format": "json", "resultType": "core", "pageSize": 1})
    resp.raise_for_status()
    results = resp.json().get("resultList", {}).get("result", [])
    return parse_result(results[0]) if results else None
