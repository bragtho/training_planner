"""Gemeinsame Helfer: Europe-PMC-Antworten, Fake-Backend und Fake-KI (keine echten Netz- oder KI-Aufrufe)."""

from __future__ import annotations

import json
import os
import tempfile

import httpx
import pytest

# Tests duerfen nie die echte config.json (mit Verwaltungsschluessel) lesen oder ueberschreiben
os.environ["WISSENS_MANAGER_CONFIG"] = os.path.join(tempfile.mkdtemp(prefix="wm-test-"), "config.json")

from wissens_manager.ai import AiError


def epmc_result(i: int = 1, **kw) -> dict:
    base = {
        "id": str(1000 + i), "source": "MED", "pmid": str(1000 + i), "doi": f"10.1000/Paper.{i}",
        "title": f"Interval training in cyclists {i}.", "authorString": "Seiler S, Kjerland GO",
        "journalTitle": "Sports Med", "pubYear": "2024", "isOpenAccess": "N", "citedByCount": 10 + i,
        "abstractText": f"<h4>Background</h4> High-intensity interval training improves VO2max in trained cyclists (study {i}). "
                        "Twelve riders completed 4 x 4 min intervals.",
        "pubTypeList": {"pubType": ["Meta-Analysis", "Journal Article"]},
    }
    return base | kw


def epmc_response(results: list[dict], next_cursor: str | None = None) -> dict:
    return {"hitCount": len(results), "nextCursorMark": next_cursor or "END", "resultList": {"result": results}}


class FakeBackend:
    """Verhaelt sich wie BackendClient, speichert alles im Speicher."""

    def __init__(self, known_dois=(), known_pmids=(), cards=(), sources=()):
        self._known = {"dois": list(known_dois), "pmids": list(known_pmids)}
        self._cards = list(cards)
        self._sources = list(sources)
        self.candidates_db: list[dict] = []
        self.decisions: list[tuple] = []
        self.accepted: list[dict] = []
        self.saved: list[tuple] = []
        self.retired: list[tuple] = []

    def known(self):
        k = {"dois": list(self._known["dois"]), "pmids": list(self._known["pmids"])}
        for c in self.candidates_db:
            if c["doi"]:
                k["dois"].append(c["doi"])
            if c["pmid"]:
                k["pmids"].append(c["pmid"])
        return k

    def cards(self, status=None):
        return [c for c in self._cards if not status or c["status"] == status]

    def sources(self):
        return list(self._sources)

    def ingest(self, items):
        known = self.known()
        created = skipped = 0
        for it in items:
            if (it["doi"] and it["doi"] in known["dois"]) or (it["pmid"] and it["pmid"] in known["pmids"]):
                skipped += 1
                continue
            self.candidates_db.append({"id": len(self.candidates_db) + 1, "status": "pending", "created_at": "2026-10-07T10:00:00+00:00", **it})
            created += 1
        return {"created": created, "skipped": skipped}

    def candidates(self, status=None):
        return [c for c in self.candidates_db if not status or c["status"] == status]

    def decide(self, cid, action, note=None, card=None, sources=None):
        c = next(c for c in self.candidates_db if c["id"] == cid)
        c["status"] = {"reject": "rejected", "watch": "watch", "accept": "accepted"}[action]
        c["decision_note"] = note
        self.decisions.append((cid, action, note))
        if action == "accept":
            self.accepted.append({"card": card, "sources": sources, "note": note})
            self._cards = [x for x in self._cards if x["slug"] != card["slug"]] + [
                {**card, "topic_label": card["topic"], "version": 1, "review_overdue": False, "claims": [],
                 "sources": [{**x, "citation": x["key"], "design_label": x["design"]} for x in (sources or [])]}]
        return {"candidate": c}

    def ping(self):
        k = self.known()
        return {"dois": len(k["dois"]), "pmids": len(k["pmids"])}

    def card(self, slug):
        return next(c for c in self._cards if c["slug"] == slug)

    def put_card(self, slug, body):
        self.saved.append((slug, body))
        return body

    def retire(self, slug, note=None):
        self.retired.append((slug, note))
        for c in self._cards:
            if c["slug"] == slug:
                c["status"] = "retired"
        return {}

    def history(self, slug):
        return [{"version": 1, "action": "created", "note": "Start", "changed_at": "2026-10-04T10:00:00+00:00",
                 "snapshot": {"recommendation": "Wenn X, dann Y."}}]

    def export(self):
        return {"cards": self._cards}


class FakeAi:
    """Liefert vorbereitete Bewertungen je Studien-ID (P1, P2, ...) und merkt sich die Aufrufe."""

    def __init__(self, relevant=None, fail_on=None, limit_after=None):
        self.relevant = relevant or {}  # Nummer der Studien-ID (1 fuer P1) -> Teil-Ergebnis
        self.calls = 0
        self.total_cost_usd = 0.0
        self.prompts: list[str] = []
        self.fail_on = fail_on
        self.plan = None
        self.limit_after = limit_after

    def run_json(self, system, prompt, schema):
        from wissens_manager.ai import AiLimitError

        self.prompts.append(prompt)
        if self.limit_after is not None and self.calls >= self.limit_after:
            raise AiLimitError("Abo-Grenze erreicht")
        self.calls += 1
        self.total_cost_usd += 0.01
        ids = [line[1:line.index("]")] for line in prompt.splitlines() if line.startswith("[P")]
        if self.fail_on and self.fail_on in prompt:
            raise AiError("Zeitüberschreitung")
        if "Suchplan fuer diese Forschungsfrage" in prompt:
            self.plan_requests = getattr(self, "plan_requests", []) + [prompt]
            return self.plan or {"queries": ['TITLE_ABS:("interval training") AND TITLE_ABS:(cycling OR cyclists)',
                                             'TITLE_ABS:(HIIT) AND TITLE_ABS:(cyclists)'],
                                 "topic": "intervalle", "label": "Intervalle", "note": "Sucht Intervallstudien."}
        if "Pruefe jede Auswertung" in prompt:
            return {"results": [{"id": i, "verdict": "ok", "issues": []} for i in ids]}
        return {"results": [{**self.default(pid), **self.relevant.get(int(pid[1:]), {})} for pid in ids]}

    @staticmethod
    def default(pid):
        return {"id": pid, "relevant": True, "relevance_reason": "Passt", "design": "meta_analysis", "population": "trainierte Radfahrer",
                "sample_n": 120, "summary": "Intervalle verbessern die VO2max.", "finding": "Mehr VO2max.",
                "quotes": ["High-intensity interval training improves VO2max in trained cyclists"], "limitations": "Kleine Studien.",
                "directness": "direct", "suggested_action": "new_card", "target_card": None, "evidence_suggestion": "A",
                "card_draft": {"slug": "intervalle-vo2max", "title": "Intervalle und VO2max", "tags": ["vo2max"],
                               "summary": "Intervalle steigern die VO2max.", "recommendation": "Wenn VO2max das Ziel ist, dann Intervalle.",
                               "caveats": None, "applies_to": {"population": ["trained"], "sex": "all", "age": None}, "safety": False,
                               "claims": [{"text": "Intervalle steigern die VO2max.",
                                           "quote": "High-intensity interval training improves VO2max in trained cyclists"}]}}


def mock_http(routes: dict) -> httpx.Client:
    """httpx-Client mit Antworten je URL-Teilstring (Wert: dict, Liste von dicts nacheinander oder httpx.Response)."""
    state = {k: 0 for k in routes}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for part, resp in routes.items():
            if part in url:
                if isinstance(resp, httpx.Response):
                    return resp
                if isinstance(resp, list):
                    i = min(state[part], len(resp) - 1)
                    state[part] += 1
                    resp = resp[i]
                return httpx.Response(200, json=resp)
        return httpx.Response(404, json={"error": "unbekannt", "url": url})

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def crossref_ok():
    return {"message": {"title": ["Interval training in cyclists 1"], "issued": {"date-parts": [[2024]]}}}


def cli_output(payload: dict | None = None, *, error: str | None = None, text: str | None = None) -> str:
    data = {"type": "result", "is_error": bool(error), "result": error or text or "", "total_cost_usd": 0.02,
            "usage": {"input_tokens": 100, "output_tokens": 50}}
    if payload is not None:
        data["structured_output"] = payload
    return json.dumps(data)
