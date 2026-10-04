"""Ablauf einer Recherche: suchen, bekannte aussortieren, KI bewerten, KI gegenpruefen, deterministisch pruefen, ans Backend melden."""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import httpx

from . import ai as ai_mod
from . import europepmc, topics, verify
from .backend import BackendClient
from .europepmc import Paper

Progress = Callable[[str, int, int, str], None]
MAX_CLAIM_WORDS = 25


@dataclass
class ResearchOptions:
    topic: str
    free_text: str = ""
    study_types: tuple[str, ...] = topics.DEFAULT_STUDY_TYPES
    year_from: int | None = None
    max_papers: int = 20
    batch_size: int = 5
    parallel: int = 2


@dataclass
class RunSummary:
    found: int = 0
    evaluated: int = 0
    relevant: int = 0
    auto_rejected: int = 0
    ingested: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    ai_calls: int = 0
    cost_usd: float = 0.0
    stopped: bool = False

    def text(self) -> str:
        parts = [f"{self.found} neue Studien gefunden, {self.evaluated} ausgewertet", f"{self.relevant} relevant zur Prüfung vorgemerkt",
                 f"{self.auto_rejected} als nicht relevant aussortiert"]
        if self.skipped:
            parts.append(f"{self.skipped} waren dem Backend schon bekannt")
        if self.stopped:
            parts.append("vorzeitig beendet")
        if self.errors:
            parts.append(f"{len(self.errors)} Fehler")
        return ", ".join(parts)


def _batches(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _existing_cards(backend: BackendClient, topic: str) -> list[dict]:
    return [{"slug": c["slug"], "title": c["title"], "evidence": c["evidence"]}
            for c in backend.cards() if c["topic"] == topic and c["status"] != "retired"]


def build_checks(paper: Paper, ai_result: dict, cross: dict | None, crossref: dict | None) -> dict:
    """Deterministische Pruefungen fuer einen Kandidaten (Zitate, Rueckzug, Metadaten) plus das Urteil der Gegenpruefung."""
    claim_quotes = [c.get("quote", "") for c in ((ai_result.get("card_draft") or {}).get("claims") or [])]
    quotes = verify.check_quotes(ai_result.get("quotes", []), paper.abstract)
    claims = verify.check_quotes(claim_quotes, paper.abstract)
    too_long = [q for q in ai_result.get("quotes", []) + claim_quotes if len(q.split()) > MAX_CLAIM_WORDS]
    return {
        "quotes": quotes, "claim_quotes": claims,
        "all_quotes_found": bool(quotes) and all(q["found"] for q in quotes + claims),
        "quotes_too_long": len(too_long),
        "cross_check": cross or {"verdict": "unchecked", "issues": []},
        "retraction": verify.retraction_status(paper, crossref),
        "metadata_ok": verify.metadata_matches(paper, crossref),
    }


def evaluate(papers: list[Paper], topic: str, *, backend: BackendClient, ai: ai_mod.AiAdapter, batch_size: int = 5, parallel: int = 2,
             crossref_http: httpx.Client | None = None, progress: Progress = lambda *a: None,
             cancelled: Callable[[], bool] = lambda: False) -> tuple[list[dict], RunSummary]:
    """Bewertet Studien mit der KI und baut die Kandidaten fuer das Backend (noch nicht gesendet)."""
    summary = RunSummary(found=len(papers))
    label = topics.topic_label(topic)
    existing = _existing_cards(backend, topic)
    taken_keys = {s["key"] for s in backend.sources()}

    ids = {f"P{i + 1}": p for i, p in enumerate(papers)}
    batches = _batches(list(ids.items()), batch_size)
    triaged: dict[str, dict] = {}
    limit_hit = False

    def run_triage(batch: list[tuple[str, Paper]]) -> dict[str, dict]:
        return ai_mod.triage(ai, label, existing, dict(batch))

    progress("bewerten", 0, len(batches), f"KI bewertet {len(papers)} Studien in {len(batches)} Paketen ...")
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = []
        for b in batches:
            if cancelled():
                summary.stopped = True
                break
            futures.append(pool.submit(run_triage, b))
        for i, f in enumerate(futures):
            try:
                triaged.update(f.result())
            except ai_mod.AiLimitError as e:
                limit_hit = True
                summary.errors.append(str(e))
            except ai_mod.AiError as e:
                summary.errors.append(str(e))
            progress("bewerten", i + 1, len(batches), f"Paket {i + 1} von {len(batches)} bewertet")
    summary.stopped = summary.stopped or limit_hit or cancelled()
    summary.evaluated = len(triaged)

    relevant = {pid: (ids[pid], r) for pid, r in triaged.items() if r["suggested_action"] != "irrelevant"}
    cross: dict[str, dict] = {}
    if relevant and not summary.stopped:
        cbatches = _batches(list(relevant.items()), batch_size)
        progress("gegenpruefen", 0, len(cbatches), "KI prüft die Aussagen gegen die Abstracts ...")
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            futs = [pool.submit(ai_mod.cross_check, ai, dict(b)) for b in cbatches]
            for i, f in enumerate(futs):
                try:
                    cross.update(f.result())
                except ai_mod.AiError as e:
                    summary.errors.append(str(e))
                progress("gegenpruefen", i + 1, len(cbatches), f"Gegenprüfung {i + 1} von {len(cbatches)}")

    items: list[dict] = []
    total = len(triaged)
    for n, (pid, res) in enumerate(triaged.items(), start=1):
        paper = ids[pid]
        progress("pruefen", n, total, f"Prüfe Quelle {n} von {total}: {paper.title[:60]}")
        crossref = verify.crossref_work(paper.doi, http=crossref_http) if paper.doi and res["suggested_action"] != "irrelevant" else None
        checks = build_checks(paper, res, cross.get(pid), crossref)
        suggested_source = None
        if res["suggested_action"] != "irrelevant":
            key = verify.source_key(paper, taken_keys)
            taken_keys.add(key)
            suggested_source = {
                "key": key, "authors": paper.authors, "year": paper.year, "title": paper.title, "journal": paper.journal,
                "doi": paper.doi, "pmid": paper.pmid, "design": res["design"], "sample_n": res["sample_n"],
                "population": res["population"] or None, "basis": "abstract",
                "retracted": checks["retraction"]["status"] == "retracted",
                "retraction_checked": dt.date.today().isoformat() if crossref is not None else None,
            }
        items.append({
            "doi": paper.doi, "pmid": paper.pmid, "title": paper.title, "topic": topic,
            "analysis": {"paper": paper.to_dict(), "ai": res, "check": checks, "suggested_source": suggested_source,
                         "auto_rejected": res["suggested_action"] == "irrelevant"},
        })
        if res["suggested_action"] != "irrelevant":
            summary.relevant += 1
        else:
            summary.auto_rejected += 1
    summary.ai_calls = getattr(ai, "calls", 0)
    summary.cost_usd = getattr(ai, "total_cost_usd", 0.0)
    return items, summary


def send(items: list[dict], backend: BackendClient, summary: RunSummary) -> None:
    """Meldet Kandidaten ans Backend; automatisch aussortierte werden sofort als verworfen vermerkt (damit sie nicht wiederkehren)."""
    for chunk in _batches(items, 50):
        res = backend.ingest(chunk)
        summary.ingested += res["created"]
        summary.skipped += res["skipped"]
    auto = {(i["doi"], i["pmid"]) for i in items if i["analysis"]["auto_rejected"]}
    if not auto:
        return
    for c in backend.candidates("pending"):
        if (c["doi"], c["pmid"]) in auto and c["analysis"].get("auto_rejected"):
            reason = (c["analysis"].get("ai") or {}).get("relevance_reason") or "nicht relevant"
            backend.decide(c["id"], "reject", f"Automatisch: {reason}"[:480])


def run_research(opts: ResearchOptions, *, backend: BackendClient, ai: ai_mod.AiAdapter, epmc_http: httpx.Client | None = None,
                 crossref_http: httpx.Client | None = None, progress: Progress = lambda *a: None,
                 cancelled: Callable[[], bool] = lambda: False) -> RunSummary:
    known = backend.known()
    known_dois, known_pmids = set(known["dois"]), set(known["pmids"])
    query = topics.build_query(opts.topic, opts.free_text, opts.study_types, opts.year_from)
    progress("suchen", 0, 1, "Suche bei Europe PMC ...")
    papers = europepmc.search(query, limit=opts.max_papers, http=epmc_http,
                              skip=lambda p: (p.doi in known_dois) or (p.pmid in known_pmids))
    progress("suchen", 1, 1, f"{len(papers)} neue Studien mit Abstract gefunden")
    if not papers:
        return RunSummary(found=0)
    items, summary = evaluate(papers, opts.topic, backend=backend, ai=ai, batch_size=opts.batch_size, parallel=opts.parallel,
                              crossref_http=crossref_http, progress=progress, cancelled=cancelled)
    progress("senden", 0, 1, "Sende Ergebnisse ans Backend ...")
    send(items, backend, summary)
    progress("senden", 1, 1, summary.text())
    return summary


def analyze_identifier(identifier: str, topic: str, *, backend: BackendClient, ai: ai_mod.AiAdapter, epmc_http: httpx.Client | None = None,
                       crossref_http: httpx.Client | None = None, progress: Progress = lambda *a: None) -> RunSummary:
    """Wertet eine einzelne Studie per DOI oder PMID aus (auch wenn sie nicht zu den Standardthemen-Treffern gehoert)."""
    paper = europepmc.fetch(identifier, http=epmc_http)
    if paper is None:
        raise ValueError(f"Keine Studie zu '{identifier}' bei Europe PMC gefunden")
    if not paper.abstract:
        raise ValueError("Die Studie hat bei Europe PMC keinen Abstract und kann nicht ausgewertet werden")
    known = backend.known()
    if (paper.doi and paper.doi in known["dois"]) or (paper.pmid and paper.pmid in known["pmids"]):
        raise ValueError("Diese Studie ist dem Backend schon bekannt (als Quelle oder Kandidat)")
    items, summary = evaluate([paper], topic, backend=backend, ai=ai, batch_size=1, parallel=1, crossref_http=crossref_http, progress=progress)
    send(items, backend, summary)
    return summary
