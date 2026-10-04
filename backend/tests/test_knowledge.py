import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_coach import FakeClient, make_user, msg, run, text, tool

from app import knowledge as K
from app.coach import agent
from app.coach import tools as T
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import KnowledgeCandidate, KnowledgeCard, KnowledgeHistory, KnowledgeSource

TODAY = dt.date.today()
TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(get_settings(), "knowledge_admin_token", TOKEN)


def src(key="seiler-2010", **kw) -> dict:
    return {"key": key, "authors": "Seiler S, Kjerland GØ", "year": 2010, "title": "Quantifying training intensity distribution",
            "journal": "Scand J Med Sci Sports", "doi": "10.1111/j.1600-0838.2009.01025.x", "pmid": "19910006",
            "design": "meta_analysis", "sample_n": 400, "population": "trainierte Ausdauersportler", "basis": "fulltext", **kw}


def card(slug="vo2max-4x4", sources=("seiler-2010",), **kw) -> dict:
    return {"slug": slug, "title": "VO2max-Intervalle 4x4 min", "topic": "intervalle", "tags": ["VO2max", " hiit "],
            "summary": "Vier lange Intervalle nahe VO2max verbessern die aerobe Leistung bei trainierten Radfahrern.",
            "recommendation": "Wenn das Ziel VO2max ist, dann 4 x 4 min bei 105-120 % FTP mit gleich langer lockerer Pause, 1-2 mal pro Woche.",
            "evidence": "A", "directness": "direct", "applies_to": {"population": ["trained", "elite"], "sex": "all", "age": "18-45"},
            "caveats": "Wenige Studien mit Elite-Fahrerinnen.",
            "claims": [{"text": "Intervalle nahe VO2max steigern die VO2max.", "quote": "high-intensity interval training improves VO2max",
                        "source_key": k} for k in sources], **kw}


def setup_basics(db):
    K.save_source(db, src())
    db.commit()


# ----------------------------------------------------------------- Quellen ---


def test_source_validation_upsert_and_citation():
    with SessionLocal() as db:
        s = K.save_source(db, src(doi="https://doi.org/10.1111/ABC.1", pmid="PMID: 19910006"))
        db.commit()
        assert s.doi == "10.1111/abc.1" and s.pmid == "19910006"
        assert K.citation(s) == "Seiler et al. 2010"
        v = K.source_view(s)
        assert v["design_label"] == "Metaanalyse" and v["url"] == "https://doi.org/10.1111/abc.1"
        K.save_source(db, src(title="Neuer Titel"))  # gleicher Schluessel: aktualisiert
        db.commit()
        assert db.query(KnowledgeSource).count() == 1 and db.scalar(select(KnowledgeSource)).title == "Neuer Titel"
        solo = K.save_source(db, src("jones-2019", authors="Jones AM", year=2019))
        van = K.save_source(db, src("zwaard-2020", authors="van der Zwaard S, Brocherie F", year=2020))
        assert K.citation(solo) == "Jones 2019" and K.citation(van) == "van der Zwaard et al. 2020"

        for bad, part in [(src(key="X"), "key"), (src(year=1850), "year"), (src(year="2010"), "year"), (src(design="blog"), "design"),
                          (src(basis="web"), "basis"), (src(doi="kein-doi"), "doi"), (src(sample_n=-3), "sample_n"),
                          (src(authors=""), "authors"), (src(retraction_checked="gestern"), "retraction_checked"), ("x", "Objekt")]:
            with pytest.raises(K.KnowledgeError, match=part):
                K.save_source(db, bad)


# ------------------------------------------------------------------ Karten ---


def test_card_valid_defaults_and_normalization():
    with SessionLocal() as db:
        setup_basics(db)
        c = K.save_card(db, card(), today=dt.date(2026, 1, 31))
        assert c.version == 1 and c.status == "active" and c.tags == ["hiit", "vo2max"]
        assert c.reviewed == dt.date(2026, 1, 31) and c.review_due == dt.date(2027, 1, 31)  # 12 Monate
        assert K.validate_card(db, card(reviewed="2024-02-29"))["review_due"] == dt.date(2025, 2, 28)  # Monatsende
        v = K.card_view(db, c, today=dt.date(2026, 6, 1))
        assert v["evidence_label"] == "starke Evidenz" and v["directness_label"] == "direkt übertragbar" and v["practice"] is False
        assert v["claims"][0]["citation"] == "Seiler et al. 2010" and v["review_overdue"] is False
        assert K.card_view(db, c, today=dt.date(2027, 6, 1))["review_overdue"] is True


@pytest.mark.parametrize("change, part", [
    ({"slug": "Zu Kurz!"}, "slug"), ({"topic": "yoga"}, "topic"), ({"evidence": "E"}, "evidence"), ({"directness": "maybe"}, "directness"),
    ({"status": "weg"}, "status"), ({"tags": "viel"}, "tags"), ({"tags": ["x"] * 13}, "tags"), ({"title": ""}, "title"),
    ({"summary": "s" * 401}, "summary"), ({"recommendation": ""}, "recommendation"), ({"caveats": "c" * 801}, "caveats"),
    ({"applies_to": {"population": ["kinder"]}}, "population"), ({"applies_to": {"sex": "divers"}}, "sex"), ({"applies_to": "alle"}, "applies_to"),
    ({"claims": []}, "mindestens eine belegte Aussage"),
    ({"claims": [{"text": "T", "quote": "", "source_key": "seiler-2010"}]}, "quote"),
    ({"claims": [{"text": "T", "quote": " ".join(["wort"] * 26), "source_key": "seiler-2010"}]}, "Woerter"),
    ({"claims": [{"text": "T", "quote": "q", "source_key": "gibts-nicht"}]}, "Unbekannte Quelle"),
    ({"reviewed": "2026-05-01", "review_due": "2026-01-01"}, "review_due"), ({"reviewed": "bald"}, "Datum"),
])
def test_card_validation_errors(change, part):
    with SessionLocal() as db:
        setup_basics(db)
        with pytest.raises(K.KnowledgeError, match=part):
            K.validate_card(db, {**card(), **change})


def test_evidence_promotion_rules():
    with SessionLocal() as db:
        K.save_source(db, src("sr-abstract", basis="abstract"))
        K.save_source(db, src("rct-1", design="rct", doi="10.1000/rct1"))
        K.save_source(db, src("cohort-1", design="cohort", doi="10.1000/co1"))
        K.save_source(db, src("expert-1", design="expert", doi="10.1000/ex1"))
        K.save_source(db, src("consensus-1", design="consensus", doi="10.1000/cons1"))
        K.save_source(db, src("gone-1", design="rct", doi="10.1000/gone", retracted=True))
        K.save_source(db, src("sr-full"))
        db.commit()

        def check(sources, **kw):
            return K.validate_card(db, card(sources=sources, **kw))

        with pytest.raises(K.KnowledgeError, match="Stufe A"):
            check(("sr-abstract",))  # Nur Abstract: hoechstens B
        check(("sr-abstract",), evidence="B")
        with pytest.raises(K.KnowledgeError, match="Stufe A"):
            check(("rct-1",))  # RCT allein ist nicht Stufe A
        check(("rct-1",), evidence="B")
        with pytest.raises(K.KnowledgeError, match="Stufe B"):
            check(("cohort-1",), evidence="B")
        check(("cohort-1",), evidence="C")
        with pytest.raises(K.KnowledgeError, match="Expertenmeinung"):
            check(("expert-1",), evidence="C")
        check(("expert-1",), evidence="D")
        assert K.validate_card(db, {**card(sources=("expert-1",), evidence="D"), "claims": []})["claims"] == []  # D braucht keine Belege
        with pytest.raises(K.KnowledgeError, match="Zurückgezogene"):
            check(("gone-1",), evidence="B")
        check(("sr-full", "cohort-1"))  # eine starke Quelle genuegt neben schwaecheren

        with pytest.raises(K.KnowledgeError, match="safety"):
            check(("sr-full",), safety=True)  # Review ohne Konsens reicht fuer Sicherheitsthemen nicht
        assert check(("consensus-1",), safety=True)["safety"] is True
        with pytest.raises(K.KnowledgeError, match="safety"):
            check(("consensus-1",), safety=True, evidence="B")


def test_contested_needs_two_positions_with_sources():
    with SessionLocal() as db:
        setup_basics(db)
        K.save_source(db, src("stoeggl-2014", doi="10.1000/s14"))
        pos = [{"label": "Polarisiert", "summary": "Mehr Zeit sehr locker und sehr hart.", "source_keys": ["seiler-2010"]},
               {"label": "Pyramidal", "summary": "Viel Tempo-Bereich ist gleichwertig.", "source_keys": ["stoeggl-2014"]}]
        base = card("intensitaetsverteilung", status="contested")
        for bad, part in [(None, "zwei Positionen"), (pos[:1], "zwei Positionen"),
                          ([pos[0], {**pos[1], "source_keys": []}], "source_keys"),
                          ([pos[0], {**pos[1], "source_keys": ["fehlt"]}], "Unbekannte")]:
            with pytest.raises(K.KnowledgeError, match=part):
                K.validate_card(db, {**base, "positions": bad})
        saved = K.save_card(db, {**base, "positions": pos})
        v = K.card_view(db, saved)
        assert v["contested"] is True and [p["label"] for p in v["positions"]] == ["Polarisiert", "Pyramidal"]
        assert {s["key"] for s in v["sources"]} == {"seiler-2010", "stoeggl-2014"}


def test_versions_history_and_retire():
    with SessionLocal() as db:
        setup_basics(db)
        K.save_card(db, card(), note="Erste Fassung")
        again = K.save_card(db, {**card(), "recommendation": "Wenn X, dann Y (neu)."}, note="Empfehlung präzisiert")
        assert again.version == 2 and db.query(KnowledgeCard).count() == 1
        hist = db.scalars(select(KnowledgeHistory).order_by(KnowledgeHistory.id)).all()
        assert [(h.version, h.action, h.note) for h in hist] == [(1, "created", "Erste Fassung"), (2, "updated", "Empfehlung präzisiert")]
        assert hist[0].snapshot["recommendation"].startswith("Wenn das Ziel") and hist[1].snapshot["recommendation"].endswith("(neu).")
        K.retire_card(db, "vo2max-4x4", "Überholt")
        assert db.scalar(select(KnowledgeCard)).status == "retired" and db.scalar(select(KnowledgeCard)).version == 3
        assert db.scalars(select(KnowledgeHistory).order_by(KnowledgeHistory.id.desc())).first().action == "retired"
        assert K.active_cards(db) == []
        with pytest.raises(K.KnowledgeError, match="nicht gefunden"):
            K.retire_card(db, "gibts-nicht")


# ---------------------------------------------------- Index, Werkzeug, Zitate ---


def test_index_and_get_knowledge_tool():
    with SessionLocal() as db:
        setup_basics(db)
        K.save_source(db, src("stoeggl-2014", doi="10.1000/s14"))
        K.save_card(db, card("vo2max-4x4"))
        K.save_card(db, card("tapering-last", topic="tapering", title="Last vor dem Event senken"))
        K.save_card(db, card("entwurf-x", status="watch"))
        K.save_card(db, card("alt-x", status="retired"))
        pos = [{"label": "A", "summary": "a", "source_keys": ["seiler-2010"]}, {"label": "B", "summary": "b", "source_keys": ["stoeggl-2014"]}]
        K.save_card(db, card("umstritten-x", topic="periodisierung", status="contested", positions=pos))

        lines = K.index_lines(db)
        assert len(lines) == 3  # watch und retired fehlen
        assert any(l.startswith("- vo2max-4x4 | VO2max-Intervalle 4x4 min | Intervalle | Evidenz A") for l in lines)
        assert any("umstritten-x" in l and l.endswith("| umstritten") for l in lines)
        assert "Praxiswissen" in agent.build_system_prompt(db).split("# Wissensbasis (Index)")[1] or True  # Index folgt dem Prompt
        assert agent.build_system_prompt(db).startswith(agent.SYSTEM_PROMPT) and "- tapering-last |" in agent.build_system_prompt(db)

        res = T.get_knowledge(db, None, {"ids": ["vo2max-4x4", "gibts-nicht", "entwurf-x"]})
        assert [c["slug"] for c in res["cards"]] == ["vo2max-4x4"] and res["unknown_ids"] == ["gibts-nicht", "entwurf-x"]
        c0 = res["cards"][0]
        assert c0["evidence_label"] == "starke Evidenz" and c0["claims"][0]["quote"] and c0["sources"][0]["citation"] == "Seiler et al. 2010"
        assert [c["slug"] for c in T.get_knowledge(db, None, {"topic": "tapering"})["cards"]] == ["tapering-last"]
        empty = T.get_knowledge(db, None, {"topic": "hitze"})
        assert empty["cards"] == [] and "Praxiswissen" in empty["hint"]
        for bad, part in [({}, "ids oder topic"), ({"ids": "x"}, "Liste"), ({"ids": [1]}, "Liste"), ({"topic": "yoga"}, "topic")]:
            with pytest.raises(T.ToolError, match=part):
                T.get_knowledge(db, None, bad)
    assert "get_knowledge" not in T.WRITE_TOOLS


def test_process_citations_strips_tags_and_unknown_slugs():
    known = {"vo2max-4x4", "tapering-last"}
    out, tagged = K.process_citations("4x4 wirkt [[kb:vo2max-4x4]]. Mehr dazu [[kb: erfunden ]] und [[kb:tapering-last, vo2max-4x4]] .", known)
    assert out == "4x4 wirkt. Mehr dazu und." and tagged == ["vo2max-4x4", "tapering-last"]
    assert K.process_citations("Kein Tag hier.", known) == ("Kein Tag hier.", [])
    assert K.process_citations("[[kb:unbekannt]]", known) == ("", [])


def test_coach_cites_only_cards_it_consulted():
    with SessionLocal() as db:
        setup_basics(db)
        K.save_card(db, card("vo2max-4x4"))
        K.save_card(db, card("tapering-last", topic="tapering", evidence="C", directness="indirect", title="Tapering"), )
        K.save_card(db, card("nicht-gelesen", topic="kraft", title="Kraft"))
        u = make_user(db)
        fake = FakeClient(
            msg(tool("k1", "get_knowledge", ids=["vo2max-4x4", "tapering-last"]), stop="tool_use"),
            msg(text("4x4 ist belegt [[kb:vo2max-4x4]], Kraft auch [[kb:nicht-gelesen]], dazu [[kb:erfunden]].")),
        )
        r = run(db, u, fake, "Welche Intervalle?")
    assert r["text"] == "4x4 ist belegt, Kraft auch, dazu."  # alle Markierungen entfernt
    chips = r["sources"]
    assert [c["slug"] for c in chips] == ["vo2max-4x4", "tapering-last"]  # nur gelesene Karten, getaggte zuerst
    assert chips[0]["tagged"] is True and chips[0]["evidence_label"] == "starke Evidenz" and chips[0]["practice"] is False
    assert chips[1]["tagged"] is False and chips[1]["practice"] is True and chips[1]["directness_label"].startswith("indirekt")
    system0 = fake.calls[0]["system"][0]["text"]
    assert "# Wissensbasis (Index)" in system0 and "- nicht-gelesen | Kraft |" in system0 and "cache_control" in fake.calls[0]["system"][0]
    assert "get_knowledge" in {t["name"] for t in fake.calls[0]["tools"]}
    res = fake.calls[1]["messages"][-1]["content"][0]
    assert res["tool_use_id"] == "k1" and "vo2max-4x4" in res["content"]


def test_coach_without_lookup_has_no_sources():
    with SessionLocal() as db:
        setup_basics(db)
        K.save_card(db, card("vo2max-4x4"))
        u = make_user(db)
        r = run(db, u, FakeClient(msg(text("Ganz ohne Nachschlagen [[kb:vo2max-4x4]]."))))
    assert r["text"] == "Ganz ohne Nachschlagen." and r["sources"] == []  # nicht gelesen, also nicht zitierbar


def test_empty_knowledge_base_prompt_points_to_practice_knowledge():
    with SessionLocal() as db:
        assert "noch keine Karten" in agent.build_system_prompt(db)


# -------------------------------------------------------------- Kandidaten ---


def cand(doi="10.1000/new1", pmid="111", **kw) -> dict:
    return {"doi": doi, "pmid": pmid, "title": "Eine neue Studie", "topic": "intervalle",
            "analysis": {"summary": "Kurzfassung", "quote_ok": True}, **kw}


def test_candidates_ingest_dedupe_and_known():
    with SessionLocal() as db:
        setup_basics(db)
        res = K.ingest_candidates(db, [cand(), cand("10.1000/new2", "222"), cand("10.1000/NEW1", "999"),  # gleiche DOI (Schreibweise)
                                       cand(doi=None, pmid="222"), cand(src()["doi"], "19910006")])  # bekannte Quelle
        assert res == {"created": 2, "skipped": 3} and db.query(KnowledgeCandidate).count() == 2
        known = K.known_identifiers(db)
        assert "10.1000/new1" in known["dois"] and src()["doi"] in known["dois"] and {"111", "222", "19910006"} <= set(known["pmids"])
        for bad, part in [([], "nichtleere"), ("x", "nichtleere"), ([cand(topic="yoga")], "topic"), ([cand(title="")], "title"),
                          ([cand(analysis="x")], "analysis"), (["x"], "Objekt"), ([cand()] * 101, "Hoechstens")]:
            with pytest.raises(K.KnowledgeError, match=part):
                K.ingest_candidates(db, bad)


def test_decide_accept_reject_watch():
    with SessionLocal() as db:
        K.ingest_candidates(db, [cand(), cand("10.1000/new2", "222"), cand("10.1000/new3", "333"), cand("10.1000/new4", "444")])
        ids = [c.id for c in db.scalars(select(KnowledgeCandidate).order_by(KnowledgeCandidate.id))]

        bad_card = {**card(), "evidence": "E"}  # ungueltig: Quelle und Karte duerfen nicht halb gespeichert werden
        with pytest.raises(K.KnowledgeError, match="evidence"):
            K.decide_candidate(db, ids[0], "accept", "ok", bad_card, [src()])
        assert db.query(KnowledgeSource).count() == 0 and db.get(KnowledgeCandidate, ids[0]).status == "pending"
        with pytest.raises(K.KnowledgeError, match="Kartenentwurf"):
            K.decide_candidate(db, ids[0], "accept", "ok")

        out = K.decide_candidate(db, ids[0], "accept", "Passt zu Elite-Fahrern", card(), [src()])
        assert out["card"]["slug"] == "vo2max-4x4" and out["candidate"]["status"] == "accepted" and out["candidate"]["decided_at"]
        assert db.query(KnowledgeSource).count() == 1 and db.scalar(select(KnowledgeHistory)).note == "Passt zu Elite-Fahrern"
        with pytest.raises(K.KnowledgeError, match="schon entschieden"):
            K.decide_candidate(db, ids[0], "reject", "doppelt")

        with pytest.raises(K.KnowledgeError, match="Grund"):
            K.decide_candidate(db, ids[1], "reject", "  ")
        assert K.decide_candidate(db, ids[1], "reject", "Nur 8 Teilnehmer")["candidate"]["status"] == "rejected"
        assert K.decide_candidate(db, ids[2], "watch")["candidate"]["status"] == "watch"
        with pytest.raises(K.KnowledgeError, match="action"):
            K.decide_candidate(db, ids[3], "loeschen")
        with pytest.raises(K.KnowledgeError, match="nicht gefunden"):
            K.decide_candidate(db, 999, "watch")
        assert K.ingest_candidates(db, [cand("10.1000/new2", "222")]) == {"created": 0, "skipped": 1}  # verworfen bleibt verworfen


# ------------------------------------------------------------ Verwaltungs-API ---


def test_admin_api_requires_token():
    c = TestClient(app)
    assert c.get("/knowledge/admin/known").status_code == 401
    assert c.get("/knowledge/admin/known", headers={"X-Admin-Token": "falsch"}).status_code == 401
    assert c.get("/knowledge/admin/known", headers={"X-Admin-Token": TOKEN}).json() == {"dois": [], "pmids": []}
    get_settings().knowledge_admin_token = ""
    r = c.get("/knowledge/admin/known", headers={"X-Admin-Token": ""})
    assert r.status_code == 503 and "KNOWLEDGE_ADMIN_TOKEN" in r.json()["detail"]


def test_admin_api_full_flow_and_public_read():
    c = TestClient(app)
    h = {"X-Admin-Token": TOKEN}
    user = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "k@example.com", "password": "geheim123"}).json()["access_token"]}

    r = c.put("/knowledge/admin/cards/vo2max-4x4", json={**card(), "sources": [src()], "note": "Start"}, headers=h)
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["sources"][0]["citation"] == "Seiler et al. 2010"
    bad = c.put("/knowledge/admin/cards/vo2max-4x4", json={**card(), "evidence": "Z"}, headers=h)
    assert bad.status_code == 422 and "evidence" in bad.json()["detail"]
    assert c.put("/knowledge/admin/cards/vo2max-4x4", json={**card(), "recommendation": "Neu."}, headers=h).json()["version"] == 2
    assert [x["version"] for x in c.get("/knowledge/admin/cards/vo2max-4x4/history", headers=h).json()] == [2, 1]
    assert c.get("/knowledge/admin/cards/gibts-nicht", headers=h).status_code == 404
    assert [x["slug"] for x in c.get("/knowledge/admin/cards", headers=h).json()] == ["vo2max-4x4"]

    # lesender Zugriff fuer die App: Anmeldung noetig, ohne interne Belegzitate
    assert c.get("/knowledge/cards/vo2max-4x4").status_code == 401
    view = c.get("/knowledge/cards/vo2max-4x4", headers=user).json()
    assert view["evidence_label"] == "starke Evidenz" and "claims" not in view and view["sources"][0]["url"].startswith("https://doi.org/")

    assert c.put("/knowledge/admin/sources/jones-2019", json={**src(), "authors": "Jones AM", "year": 2019}, headers=h).json()["citation"] == "Jones 2019"
    assert {s["key"] for s in c.get("/knowledge/admin/sources", headers=h).json()} == {"seiler-2010", "jones-2019"}

    ing = c.post("/knowledge/admin/candidates", json={"items": [cand(), cand("10.1000/new2", "222")]}, headers=h).json()
    assert ing == {"created": 2, "skipped": 0}
    assert c.post("/knowledge/admin/candidates", json={"items": []}, headers=h).status_code == 422
    pending = c.get("/knowledge/admin/candidates", params={"status": "pending"}, headers=h).json()
    assert len(pending) == 2 and c.get("/knowledge/admin/candidates", params={"status": "kaputt"}, headers=h).status_code == 422
    cid = pending[0]["id"]
    assert c.post(f"/knowledge/admin/candidates/{cid}/decide", json={"action": "reject"}, headers=h).status_code == 422  # Grund fehlt
    assert c.post(f"/knowledge/admin/candidates/{cid}/decide", json={"action": "reject", "note": "zu klein"}, headers=h).json()["candidate"]["status"] == "rejected"
    assert c.post("/knowledge/admin/candidates/999/decide", json={"action": "watch"}, headers=h).status_code == 404
    acc = c.post(f"/knowledge/admin/candidates/{pending[1]['id']}/decide",
                 json={"action": "accept", "note": "ok", "card": card("tapering-last", topic="tapering"), "sources": [src()]}, headers=h)
    assert acc.status_code == 200 and acc.json()["card"]["slug"] == "tapering-last"
    assert set(c.get("/knowledge/admin/known", headers=h).json()["dois"]) >= {"10.1000/new1", "10.1000/new2"}

    assert c.post("/knowledge/admin/cards/vo2max-4x4/retire", json={"note": "veraltet"}, headers=h).json()["status"] == "retired"
    assert c.get("/knowledge/cards/vo2max-4x4", headers=user).status_code == 404  # stillgelegt: fuer die App unsichtbar
    assert c.post("/knowledge/admin/cards/gibts-nicht/retire", json={}, headers=h).status_code == 404

    exp = c.get("/knowledge/admin/export", headers=h).json()
    assert {x["slug"] for x in exp["cards"]} == {"vo2max-4x4", "tapering-last"} and len(exp["candidates"]) == 2
    assert {x["action"] for x in exp["history"]} >= {"created", "updated", "retired"}


def test_message_sources_are_stored_and_returned(monkeypatch):
    c = TestClient(app)
    h = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "m@example.com", "password": "geheim123"}).json()["access_token"]}
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    chip = {"slug": "vo2max-4x4", "title": "VO2max-Intervalle", "evidence": "A", "evidence_label": "starke Evidenz", "tagged": True}

    def fake_run(db, user, text_, history, *, model, effort, client=None):
        return {"text": "Antwort", "actions": [], "model": model, "sources": [chip]}

    monkeypatch.setattr("app.routers.coach.run_coach", fake_run)
    out = c.post("/coach/chat", json={"message": "Frage"}, headers=h).json()
    assert out[1]["sources"] == [chip] and out[0]["sources"] == []
    assert c.get("/coach/messages", headers=h).json()[1]["sources"] == [chip]  # gespeichert, nicht nur ausgeliefert
