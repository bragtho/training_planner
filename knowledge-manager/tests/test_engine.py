import json
import subprocess

import httpx
import pytest
from conftest import FakeAi, FakeBackend, cli_output, epmc_response, epmc_result, mock_http

from wissens_manager import ai, config, europepmc, pipeline, topics, verify
from wissens_manager.backend import BackendClient, BackendError
from wissens_manager.europepmc import Paper


# ------------------------------------------------------------------ Themen ---


def test_build_query_has_fields_types_year_and_no_preprints():
    q = topics.build_query("intervalle", year_from=2018)
    assert "TITLE_ABS:" in q and 'PUB_TYPE:"Meta-Analysis"' in q and 'PUB_TYPE:"Systematic Review"' in q
    assert 'PUB_TYPE:"Consensus Statement"' in q and "PUB_YEAR:[2018 TO 3000]" in q and q.endswith("SRC:MED")
    assert "Randomized" not in q
    assert 'PUB_TYPE:"Randomized Controlled Trial"' in topics.build_query("kraft", study_types=("trials",))
    assert topics.build_query("sonstiges", "my own query", ())  == "(my own query) AND SRC:MED"  # freie Frage ohne Typfilter
    with pytest.raises(ValueError, match="Suchanfrage"):
        topics.build_query("sonstiges")
    assert set(topics.TOPICS) == {"intervalle", "zonen", "periodisierung", "tapering", "ernaehrung", "kraft", "hitze", "hoehe",
                                  "frauen", "masters", "erholung", "sonstiges"}  # gleich wie im Backend


# ------------------------------------------------------------- Europe PMC ---


def test_parse_and_clean_abstract():
    p = europepmc.parse_result(epmc_result(1))
    assert p.title == "Interval training in cyclists 1" and p.year == 2024 and p.pmid == "1001" and p.doi == "10.1000/paper.1"
    assert p.abstract.startswith("Background High-intensity interval training") and "<" not in p.abstract
    assert p.pub_types == ["Meta-Analysis", "Journal Article"] and p.open_access is False and p.url == "https://doi.org/10.1000/paper.1"
    assert europepmc.clean_abstract("A &amp; B <sup>2</sup> <i>x</i>") == "A & B 2 x"
    assert europepmc.parse_result({"title": "T", "id": "5", "source": "MED"}).pmid == "5"


def test_search_filters_pages_and_limits():
    page1 = epmc_response([epmc_result(1), epmc_result(2, abstractText=""), epmc_result(3, pubTypeList={"pubType": ["Retracted Publication"]}),
                           epmc_result(4)], next_cursor="C2")
    page2 = epmc_response([epmc_result(1), epmc_result(5), epmc_result(6)])
    http = mock_http({"/search": [page1, page2]})
    papers = europepmc.search("q", limit=10, http=http, skip=lambda p: p.pmid == "1004")
    assert [p.pmid for p in papers] == ["1001", "1005", "1006"]  # ohne Abstract, zurueckgezogen, bekannt und doppelt aussortiert
    again = europepmc.search("q", limit=2, http=mock_http({"/search": [page1, page2]}))
    assert [p.pmid for p in again] == ["1001", "1004"]


def test_fetch_by_doi_and_pmid():
    seen = []

    def handler(request):
        seen.append(request.url.params["query"])
        return httpx.Response(200, json=epmc_response([epmc_result(7)]))

    http = httpx.Client(transport=httpx.MockTransport(handler))
    assert europepmc.fetch("https://doi.org/10.1000/Paper.7", http=http).pmid == "1007"
    assert europepmc.fetch("PMID: 1007", http=http).pmid == "1007"
    assert seen == ['DOI:"10.1000/Paper.7"', "EXT_ID:1007 AND SRC:MED"]
    assert europepmc.fetch("10.1/none", http=mock_http({"/search": epmc_response([])})) is None


# ------------------------------------------------------------------ verify ---


def test_quote_check_is_tolerant_for_typography_but_strict_for_content():
    text = "High-intensity interval training improves VO2max by 5–7% in “trained” cyclists."
    assert verify.quote_found('improves VO2max by 5-7% in "trained" cyclists', text)
    assert verify.quote_found("  HIGH-INTENSITY   interval training improves  ", text)
    assert not verify.quote_found("improves VO2max by 9% in trained cyclists", text)
    assert not verify.quote_found("", text) and not verify.quote_found("...", text)
    assert verify.check_quotes(["interval training", "erfunden"], text) == [{"quote": "interval training", "found": True},
                                                                              {"quote": "erfunden", "found": False}]


def test_retraction_and_metadata_checks():
    p = Paper(title="Interval training in cyclists 1", abstract="x", year=2024, doi="10.1000/p1")
    ok = {"title": ["Interval training in cyclists 1"], "issued": {"date-parts": [[2024]]}}
    assert verify.retraction_status(p, ok)["status"] == "ok"
    assert verify.retraction_status(p, None)["status"] == "unknown"
    assert verify.retraction_status(p, {"updated-by": [{"type": "retraction", "DOI": "10.1/r"}]})["status"] == "retracted"
    assert verify.retraction_status(Paper(title="t", abstract="x", pub_types=["Retracted Publication"]), ok)["status"] == "retracted"
    assert verify.retraction_status(p, {"updated-by": [{"type": "correction"}]})["status"] == "ok"  # Korrektur ist kein Rueckzug
    assert verify.metadata_matches(p, ok) is True and verify.metadata_matches(p, None) is None
    assert verify.metadata_matches(p, {**ok, "title": ["Ganz anderer Titel"]}) is False
    assert verify.metadata_matches(p, {**ok, "issued": {"date-parts": [[2019]]}}) is False
    assert verify.crossref_work("10.1/x", http=mock_http({"crossref": httpx.Response(404)})) is None
    assert verify.crossref_work("10.1/x", http=mock_http({"crossref": {"message": ok}})) == ok


def test_source_key_is_unique_and_ascii():
    p = Paper(title="t", abstract="x", year=2010, authors="Seiler S, Kjerland GO")
    assert verify.source_key(p, set()) == "seiler-2010"
    assert verify.source_key(p, {"seiler-2010"}) == "seiler-2010a"
    assert verify.source_key(p, {"seiler-2010", "seiler-2010a"}) == "seiler-2010b"
    assert verify.source_key(Paper(title="t", abstract="x", year=2021, authors="Rønnestad BR, Hansen J"), set()) == "ronnestad-2021"
    assert verify.source_key(Paper(title="t", abstract="x", authors=""), set()) == "studie-xxxx"


# ---------------------------------------------------------------------- KI ---


def test_parse_cli_output_variants():
    payload = {"results": [{"id": "P1"}]}
    assert ai.parse_cli_output(cli_output(payload))[0] == payload
    assert ai.parse_cli_output(cli_output(payload))[1]["cost_usd"] == 0.02
    assert ai.parse_cli_output(cli_output(text="```json\n" + json.dumps(payload) + "\n```"))[0] == payload  # ohne structured_output
    with pytest.raises(ai.AiLimitError, match="später"):
        ai.parse_cli_output(cli_output(error="Claude AI usage limit reached"))
    with pytest.raises(ai.AiError, match="Fehler"):
        ai.parse_cli_output(cli_output(error="Etwas ist schiefgelaufen"))
    with pytest.raises(ai.AiError, match="Unlesbare"):
        ai.parse_cli_output("kein json")
    with pytest.raises(ai.AiError, match="gültiges JSON"):
        ai.parse_cli_output(cli_output(text="nur Text"))
    assert ai.parse_cli_output(json.dumps([{"type": "system"}, json.loads(cli_output(payload))]))[0] == payload


def test_cli_adapter_command_environment_and_cost(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-geheim")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout=cli_output({"results": []}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    a = ai.ClaudeCliAdapter("claude", "opus", timeout=99)
    assert a.run_json("SYSTEM", "PROMPT", {"type": "object"}) == {"results": []}
    cmd, kw = calls[0]
    assert cmd[1:4] == ["-p", "--output-format", "json"] and "--bare" not in cmd  # --bare wuerde das Abo ausschalten
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--model") + 1] == "opus"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == {"type": "object"} and cmd[cmd.index("--append-system-prompt") + 1] == "SYSTEM"
    assert kw["input"] == "PROMPT" and kw["timeout"] == 99 and kw["encoding"] == "utf-8"
    assert "ANTHROPIC_API_KEY" not in kw["env"] and "ANTHROPIC_AUTH_TOKEN" not in kw["env"]  # sonst Abrechnung ueber die API
    assert str(kw["cwd"]).endswith("wissens-manager-ki")  # leerer Ordner: keine Projektdateien, keine CLAUDE.md
    assert a.calls == 1 and a.total_cost_usd == pytest.approx(0.02)


def test_cli_adapter_retries_timeouts_and_reports_limits(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    state = {"n": 0}

    def flaky(cmd, **kw):
        state["n"] += 1
        if state["n"] < 3:
            raise subprocess.TimeoutExpired(cmd, 1)
        return subprocess.CompletedProcess(cmd, 0, stdout=cli_output({"results": []}), stderr="")

    monkeypatch.setattr(subprocess, "run", flaky)
    assert ai.ClaudeCliAdapter("claude").run_json("s", "p", {}) == {"results": []} and state["n"] == 3

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd, 1)))
    with pytest.raises(ai.AiError, match="Zeitüberschreitung"):
        ai.ClaudeCliAdapter("claude", retries=1).run_json("s", "p", {})

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="429 rate limit"))
    with pytest.raises(ai.AiLimitError):
        ai.ClaudeCliAdapter("claude").run_json("s", "p", {})

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    with pytest.raises(ai.AiError, match="nicht gefunden"):
        ai.ClaudeCliAdapter("gibts-nicht").run_json("s", "p", {})

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=cli_output(error="Dienst ueberlastet (overloaded)"), stderr=""))
    with pytest.raises(ai.AiLimitError):
        ai.ClaudeCliAdapter("claude").run_json("s", "p", {})


def test_triage_cleans_unsafe_values_and_cross_check_maps_ids():
    papers = {"P1": Paper(title="t1", abstract="a"), "P2": Paper(title="t2", abstract="b")}

    class Raw:
        def run_json(self, system, prompt, schema):
            return {"results": [
                {"id": "P1", "relevant": True, "design": "unbekannt", "directness": "egal", "suggested_action": "kaputt",
                 "evidence_suggestion": "A", "quotes": [" q1 ", "", 5, "q2", "q3", "q4"], "sample_n": True, "card_draft": {"slug": "x"}},
                {"id": "P2", "relevant": True, "suggested_action": "irrelevant", "card_draft": {"slug": "y"}},
                {"id": "P9", "relevant": True}]}  # unbekannte ID wird ignoriert

    out = ai.triage(Raw(), "Intervalle", [], papers)
    assert set(out) == {"P1", "P2"}
    r1 = out["P1"]
    assert r1["design"] == "other" and r1["directness"] == "indirect" and r1["suggested_action"] == "watch" and r1["quotes"] == ["q1", "q2", "q3"]
    assert r1["sample_n"] is None and r1["card_draft"] is None  # nur bei new_card
    assert out["P2"]["relevant"] is False and out["P2"]["suggested_action"] == "irrelevant" and out["P2"]["card_draft"] is None

    class Cross:
        def run_json(self, system, prompt, schema):
            return {"results": [{"id": "P1", "verdict": "ok", "issues": []}, {"id": "P2", "verdict": "ok", "issues": ["Zahl falsch"]}]}

    res = ai.cross_check(Cross(), {"P1": (papers["P1"], {}), "P2": (papers["P2"], {})})
    assert res["P1"]["verdict"] == "ok" and res["P2"] == {"verdict": "issues", "issues": ["Zahl falsch"]}  # ok mit Mängelliste zaehlt als issues
    assert ai.cross_check(Cross(), {}) == {}


# -------------------------------------------------------------- Pipeline ---


def run(opts=None, backend=None, fake_ai=None, results=None, crossref=None, **kw):
    results = results if results is not None else [epmc_result(i) for i in range(1, 5)]
    backend = backend or FakeBackend()
    fake_ai = fake_ai or FakeAi()
    epmc = mock_http({"/search": epmc_response(results)})
    cr = mock_http({"crossref": crossref or {"message": {"title": ["Interval training in cyclists"], "issued": {"date-parts": [[2024]]}}}})
    opts = opts or pipeline.ResearchOptions("intervalle", batch_size=2, parallel=1)
    events = []
    summary = pipeline.run_research(opts, backend=backend, ai=fake_ai, epmc_http=epmc, crossref_http=cr,
                                    progress=lambda stage, d, t, m: events.append(stage), **kw)
    return summary, backend, fake_ai, events


def test_pipeline_end_to_end_ingests_relevant_and_auto_rejects_the_rest():
    backend = FakeBackend(cards=[{"slug": "vo2max-4x4", "title": "VO2max 4x4", "evidence": "A", "topic": "intervalle", "status": "active"},
                                 {"slug": "alt", "title": "Alt", "evidence": "B", "topic": "intervalle", "status": "retired"},
                                 {"slug": "kraft-1", "title": "Kraft", "evidence": "B", "topic": "kraft", "status": "active"}])
    fake = FakeAi(relevant={2: {"relevant": False, "suggested_action": "irrelevant", "relevance_reason": "Andere Population"},
                            3: {"suggested_action": "supports", "target_card": "vo2max-4x4"}})
    s, backend, fake, events = run(backend=backend, fake_ai=fake)
    assert (s.found, s.evaluated, s.relevant, s.auto_rejected, s.ingested, s.skipped) == (4, 4, 3, 1, 4, 0)
    assert s.errors == [] and s.ai_calls == 4 and s.cost_usd == pytest.approx(0.04) and "3 relevant" in s.text()
    assert events[0] == "suchen" and {"bewerten", "gegenpruefen", "pruefen", "senden"} <= set(events)
    # Vorhandene Karten des Themas stehen im Prompt (aktive, nicht stillgelegte, nicht fremde Themen)
    assert "vo2max-4x4 | VO2max 4x4 | Evidenz A" in fake.prompts[0] and "alt |" not in fake.prompts[0] and "kraft-1" not in fake.prompts[0]

    pending = backend.candidates("pending")
    assert len(pending) == 3 and [c["status"] for c in backend.candidates()].count("rejected") == 1
    assert backend.decisions == [(2, "reject", "Automatisch: Andere Population")]
    c1 = pending[0]
    a = c1["analysis"]
    assert c1["topic"] == "intervalle" and a["paper"]["abstract"].startswith("Background") and a["auto_rejected"] is False
    assert a["check"]["all_quotes_found"] is True and a["check"]["retraction"]["status"] == "ok" and a["check"]["metadata_ok"] is True
    assert a["check"]["cross_check"]["verdict"] == "ok"
    src = a["suggested_source"]
    assert src["key"] == "seiler-2024" and src["design"] == "meta_analysis" and src["basis"] == "abstract" and src["retracted"] is False
    assert [c["analysis"]["suggested_source"]["key"] for c in pending] == ["seiler-2024", "seiler-2024a", "seiler-2024b"]  # eindeutig
    assert backend.candidates("rejected")[0]["analysis"]["suggested_source"] is None


def test_pipeline_flags_invented_quotes_and_retractions():
    bad_quote = {"quotes": ["This sentence is not in the abstract at all"],
                 "card_draft": {**FakeAi.default("P1")["card_draft"], "claims": [{"text": "x", "quote": "Erfundenes Zitat"}]}}
    s, backend, _, _ = run(fake_ai=FakeAi(relevant={1: bad_quote}), results=[epmc_result(1)],
                           crossref={"message": {"title": ["Interval training in cyclists"], "issued": {"date-parts": [[2024]]},
                                                 "updated-by": [{"type": "retraction", "DOI": "10.1/r"}]}})
    chk = backend.candidates("pending")[0]["analysis"]["check"]
    assert chk["all_quotes_found"] is False and chk["quotes"][0]["found"] is False and chk["claim_quotes"][0]["found"] is False
    assert chk["retraction"]["status"] == "retracted"
    assert backend.candidates("pending")[0]["analysis"]["suggested_source"]["retracted"] is True


def test_pipeline_skips_known_studies_and_handles_empty_search():
    backend = FakeBackend(known_dois=["10.1000/paper.1"], known_pmids=["1002"])
    s, backend, fake, _ = run(backend=backend)
    assert s.found == 2 and s.ingested == 2 and fake.calls >= 1  # 1 und 2 sind bekannt, nur 3 und 4 kommen durch
    empty, _, fake2, _ = run(results=[])
    assert empty.found == 0 and fake2.calls == 0  # ohne neue Studien kein KI-Aufruf


def test_pipeline_errors_limits_and_cancel():
    s, backend, _, _ = run(fake_ai=FakeAi(fail_on="cyclists 3"), results=[epmc_result(i) for i in range(1, 5)])
    assert s.evaluated == 2 and len(s.errors) == 1 and "Zeitüberschreitung" in s.errors[0]  # Paket mit Studie 3 und 4 fehlt, Rest laeuft
    assert s.ingested == 2

    s, backend, fake, _ = run(fake_ai=FakeAi(limit_after=1))
    assert s.stopped and any("Abo-Grenze" in e for e in s.errors) and s.evaluated == 2 and s.ingested == 2  # bereits Bewertetes bleibt erhalten

    s, backend, fake, _ = run(cancelled=lambda: True)
    assert s.stopped and fake.calls == 0 and backend.candidates() == []


def test_analyze_identifier():
    kw = dict(backend=FakeBackend(), ai=FakeAi(), crossref_http=mock_http({"crossref": {"message": {"title": ["Interval training in cyclists 7"],
                                                                                                    "issued": {"date-parts": [[2024]]}}}}))
    s = pipeline.analyze_identifier("10.1000/Paper.7", "intervalle", epmc_http=mock_http({"/search": epmc_response([epmc_result(7)])}), **kw)
    assert s.ingested == 1 and s.relevant == 1
    with pytest.raises(ValueError, match="Keine Studie"):
        pipeline.analyze_identifier("10.1/x", "intervalle", epmc_http=mock_http({"/search": epmc_response([])}), **kw)
    with pytest.raises(ValueError, match="keinen Abstract"):
        pipeline.analyze_identifier("10.1/x", "intervalle", epmc_http=mock_http({"/search": epmc_response([epmc_result(8, abstractText="")])}),
                                    backend=FakeBackend(), ai=FakeAi())
    with pytest.raises(ValueError, match="schon bekannt"):
        pipeline.analyze_identifier("10.1000/paper.9", "intervalle", epmc_http=mock_http({"/search": epmc_response([epmc_result(9)])}),
                                    backend=FakeBackend(known_dois=["10.1000/paper.9"]), ai=FakeAi())


# ---------------------------------------------------- Backend-Client, Konfig ---


def test_backend_client_headers_errors_and_paths():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.headers.get("x-admin-token"), request.url.params.get("status")))
        if request.url.path.endswith("/known"):
            return httpx.Response(200, json={"dois": ["a"], "pmids": []})
        if request.url.path.endswith("/candidates") and request.method == "POST":
            return httpx.Response(422, json={"detail": "items muss eine nichtleere Liste sein"})
        if request.url.path.endswith("/cards/x/retire"):
            return httpx.Response(401, json={"detail": "Ungueltiger Verwaltungsschluessel"})
        return httpx.Response(200, json=[])

    c = BackendClient("http://localhost:8000/", "tok", http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.ping() == {"dois": 1, "pmids": 0} and seen[0] == ("GET", "/knowledge/admin/known", "tok", None)
    c.candidates("pending")
    assert seen[-1][1] == "/knowledge/admin/candidates" and seen[-1][3] == "pending"
    with pytest.raises(BackendError, match="nichtleere Liste"):
        c.ingest([])
    with pytest.raises(BackendError, match="KNOWLEDGE_ADMIN_TOKEN"):
        c.retire("x")

    def boom(request):
        raise httpx.ConnectError("refused")

    down = BackendClient("http://localhost:1", "t", http=httpx.Client(transport=httpx.MockTransport(boom)))
    with pytest.raises(BackendError, match="nicht erreichbar"):
        down.known()


def test_config_roundtrip_clamp_and_broken_file(tmp_path):
    path = tmp_path / "config.json"
    assert config.load_config(path).backend_url == "http://localhost:8000"
    cfg = config.Config(backend_url=" http://x:9/ ", parallel=9, batch_size=0, max_papers=500, ai_timeout=1, admin_token="t")
    config.save_config(cfg, path)
    loaded = config.load_config(path)
    assert (loaded.backend_url, loaded.parallel, loaded.batch_size, loaded.max_papers, loaded.ai_timeout) == ("http://x:9", 3, 1, 100, 30)
    path.write_text("{kaputt", encoding="utf-8")
    assert config.load_config(path).parallel == 2  # kaputte Datei: Standardwerte
    path.write_text(json.dumps({"model": "opus", "unbekannt": 1}), encoding="utf-8")
    assert config.load_config(path).model == "opus"
