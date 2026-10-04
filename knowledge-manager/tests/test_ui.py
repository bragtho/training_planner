"""Oberflaechentests im Offscreen-Modus: Recherche -> Ergebnisse -> Aufnehmen/Verwerfen, Editor-Regeln, Wissensbasis."""

import os
import sys
import time
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from conftest import FakeAi, FakeBackend, epmc_response, epmc_result, mock_http
from PyQt6.QtWidgets import QApplication, QDialog, QInputDialog, QMessageBox

from wissens_manager import __version__
from wissens_manager.config import Config
from wissens_manager.ui import knowledge_tab, results_tab
from wissens_manager.ui.card_editor import CardEditorDialog
from wissens_manager.ui.core import Services, stylesheet
from wissens_manager.ui.main_window import MainWindow
from wissens_manager.ui.render import candidate_html, candidate_title, card_html, evidence_cap
from wissens_manager.ui.results_tab import capped_evidence

app = QApplication.instance() or QApplication([])

# PyQt6 beendet das Programm bei unbehandelten Fehlern in Slots. Der Handler sammelt sie, jeder Test schlaegt dann mit der Meldung fehl.
_errors: list[str] = []
sys.excepthook = lambda t, v, tb: _errors.append("".join(traceback.format_exception(t, v, tb)))


@pytest.fixture(autouse=True)
def no_unhandled_errors():
    _errors.clear()
    yield
    assert not _errors, _errors[0]


def wait_for(cond, timeout=8.0):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    app.processEvents()
    return cond()


def settle(*tabs):
    """Wartet, bis alle Hintergrundaufgaben der Reiter fertig sind."""
    wait_for(lambda: all(not (getattr(t, "_task", None) and t._task.isRunning()) for t in tabs))
    app.processEvents()


@pytest.fixture
def services():
    backend = FakeBackend()
    epmc = mock_http({"/search": epmc_response([epmc_result(i) for i in range(1, 4)])})
    crossref = mock_http({"crossref": {"message": {"title": ["Interval training in cyclists"], "issued": {"date-parts": [[2024]]}}}})
    return Services(Config(batch_size=3, parallel=1), backend, FakeAi(relevant={3: {"relevant": False, "suggested_action": "irrelevant",
                                                                                      "relevance_reason": "Andere Population"}}),
                    epmc_http=epmc, crossref_http=crossref)


@pytest.fixture
def window(services, monkeypatch):
    app.setStyleSheet(stylesheet(dark=False))
    w = MainWindow(Config(), services, check_connections=False)
    yield w
    for t in (w.research, w.results, w.knowledge):
        task = getattr(t, "_task", None)
        if task:
            task.wait(3000)
    w.close()


def run_research(window):
    window.research.topic.setCurrentIndex(window.research.topic.findData("intervalle"))
    window.research.start()
    settle(window.research)
    settle(window.results)
    wait_for(lambda: window.results.list.count() > 0)


# --------------------------------------------------------------- Darstellung ---


def test_render_functions():
    assert evidence_cap("abstract") == "B" and evidence_cap("fulltext") == "A"
    assert capped_evidence("A", "abstract") == "B" and capped_evidence("A", "fulltext") == "A" and capped_evidence("C", "abstract") == "C"
    assert capped_evidence("Z", "fulltext") == "C" and capped_evidence(None, "abstract") == "C"
    cand = {"id": 1, "title": "<b>Titel</b>", "topic": "intervalle", "status": "pending", "decision_note": None, "analysis": {
        "paper": {"authors": "Seiler S", "journal": "J", "year": 2024, "doi": "10.1/x", "url": "https://doi.org/10.1/x", "pub_types": ["Meta-Analysis"],
                  "abstract": "Abstract <script>"},
        "ai": {"suggested_action": "supports", "target_card": "vo2max-4x4", "design": "meta_analysis", "population": "trainierte", "sample_n": 40,
               "directness": "direct", "summary": "Kurz", "finding": "Befund", "limitations": "Klein", "evidence_suggestion": "A",
               "card_draft": {"title": "T", "slug": "t", "recommendation": "Wenn X, dann Y."}},
        "check": {"quotes": [{"quote": "echt", "found": True}, {"quote": "falsch", "found": False}], "claim_quotes": [], "quotes_too_long": 0,
                  "cross_check": {"verdict": "issues", "issues": ["Zahl falsch"]}, "retraction": {"status": "retracted", "reason": "Crossref: retraction"},
                  "metadata_ok": False},
        "suggested_source": {"basis": "abstract"}}}
    html = candidate_html(cand)
    assert "&lt;b&gt;Titel" in html and "&lt;script&gt;" in html and "<script>" not in html  # nichts Fremdes wird als HTML ausgefuehrt
    assert "vo2max-4x4" in html and "Zahl falsch" in html and "Crossref: retraction" in html and "höchstens <b>B</b>" in html
    assert "1 von 2 Belegzitaten stehen NICHT" in html and "weichen von Crossref ab" in html
    assert "zurückgezogen" in candidate_title(cand)
    card = {"slug": "s", "title": "Karte", "topic_label": "Intervalle", "evidence": "C", "directness": "indirect", "status": "contested", "safety": True,
            "review_overdue": True, "review_due": "2026-01-01", "recommendation": "R", "summary": "S", "applies_to": {"population": ["elite"], "sex": "all"},
            "positions": [{"label": "Lager A", "summary": "a", "source_keys": ["k"]}], "claims": [{"text": "T", "quote": "Q", "citation": "Seiler 2010"}],
            "sources": [{"citation": "Seiler 2010", "title": "T", "design_label": "RCT", "basis": "abstract", "url": "https://x"}], "version": 2,
            "reviewed": "2025-01-01"}
    h = card_html(card)
    assert "Überprüfung fällig" in h and "sicherheitsrelevant" in h and "Lager A" in h and "nur Abstract" in h and "Version 2" in h


# --------------------------------------------------------------- Ablauf ---


def test_main_window_starts_with_three_areas(window):
    assert window.tabs.count() == 3 and f"Wissens-Manager {__version__}" == window.windowTitle()


def test_research_flow_fills_results(window, services):
    run_research(window)
    log = window.research.log.toPlainText()
    assert "Recherche „Intervalle“" in log and "Fertig:" in log and "relevant" in log
    assert window.research.start_btn.isEnabled() and not window.research.cancel_btn.isEnabled()
    assert window.tabs.currentWidget() is window.results  # springt zu den Ergebnissen
    assert window.results.list.count() == 2  # Studie 3 wurde als nicht relevant aussortiert
    assert "KI-Vorschlag" in window.results.detail.toHtml() or "Neue Karte vorgeschlagen" in window.results.detail.toPlainText()
    assert window.results.accept_btn.isEnabled() and window.results.reject_btn.isEnabled()
    rejected = [c for c in services.backend.candidates() if c["status"] == "rejected"]
    assert len(rejected) == 1 and rejected[0]["decision_note"].startswith("Automatisch")
    window.results.status.setCurrentIndex(window.results.status.findData("rejected"))
    settle(window.results)
    wait_for(lambda: window.results.list.count() == 1)
    assert not window.results.accept_btn.isEnabled()  # nur Offenes laesst sich entscheiden


def test_research_validates_input(window, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    window.research.topic.setCurrentIndex(window.research.topic.findData("sonstiges"))
    window.research.start()
    assert shown and "Suchanfrage" in shown[0] and not window.research.cancel_btn.isEnabled()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    window.research.analyze_one()
    assert "DOI oder PMID" in shown[-1]


def test_accept_candidate_opens_editor_with_capped_evidence_and_saves(window, services, monkeypatch):
    run_research(window)
    submitted = {}

    def fake_exec(self):
        assert self.evidence.currentData() == "B"  # KI schlug A vor, nur Abstract: B
        assert self.windowTitle().startswith("Neue Karte") and "höchstens Evidenzstufe B" in self.cap_hint.text()
        assert self.claims_table.item(0, 3).text().startswith("✓")  # Zitat steht im Abstract
        self.note.setText("Passt zu Elite-Fahrern")
        self._save()
        submitted["error"] = self.error.text()
        return 1 if self.result() == QDialog.DialogCode.Accepted else 0

    monkeypatch.setattr(CardEditorDialog, "exec", fake_exec)
    window.results.accept_candidate()
    settle(window.results)
    assert submitted["error"] == ""
    acc = services.backend.accepted[0]
    assert acc["note"] == "Passt zu Elite-Fahrern"
    card, src = acc["card"], acc["sources"][0]
    assert card["slug"] == "intervalle-vo2max" and card["topic"] == "intervalle" and card["evidence"] == "B" and card["status"] == "active"
    assert card["claims"][0]["source_key"] == src["key"] == "seiler-2024a" and card["applies_to"]["population"] == ["trained"]
    assert src["basis"] == "abstract" and src["design"] == "meta_analysis" and src["doi"] == "10.1000/paper.2" and src["retracted"] is False
    assert src["retraction_checked"]  # Pruefdatum aus dem Crossref-Abgleich bleibt erhalten


def test_editor_blocks_quotes_missing_in_abstract_until_fulltext_is_confirmed(window):
    paper = {"doi": "10.1000/paper.1", "abstract": "High-intensity interval training improves VO2max in trained cyclists."}
    src = {"key": "seiler-2024", "authors": "Seiler S", "year": 2024, "title": "T", "doi": "10.1000/paper.1", "design": "meta_analysis", "basis": "abstract"}
    card = {"slug": "k-1", "title": "K", "topic": "intervalle", "summary": "S", "recommendation": "R", "evidence": "B", "directness": "direct",
            "claims": [{"text": "Aussage", "quote": "Das steht nirgends im Abstract", "source_key": "seiler-2024"}]}
    sent = []
    dlg = CardEditorDialog(window, heading="Test", card=card, sources=[src], paper=paper, submit=lambda *a: sent.append(a))
    assert dlg.claims_table.item(0, 3).text().startswith("✗")
    dlg._save()
    assert "nicht im Abstract" in dlg.error.text() and sent == []
    dlg.sources_table.cellWidget(0, 10).setCurrentIndex(1)  # „Volltext selbst gelesen“: Nutzer bestaetigt
    assert "Volltext" in dlg.cap_hint.text()
    dlg._save()
    assert dlg.error.text() == "" and len(sent) == 1 and sent[0][1][0]["basis"] == "fulltext"
    # zu langes Zitat und kaputte Zahl werden lokal gemeldet
    dlg2 = CardEditorDialog(window, heading="Test", card=card, sources=[src], paper=paper, submit=lambda *a: None)
    dlg2.claims_table.item(0, 1).setText(" ".join(["wort"] * 30))
    assert "höchstens 25" in dlg2.claims_table.item(0, 3).text()
    dlg2.sources_table.item(0, 2).setText("zweitausend")
    dlg2._save()
    assert "Jahr muss eine Zahl sein" in dlg2.error.text()


def test_editor_shows_backend_errors_and_stays_open(window):
    def refuse(card, sources, note):
        raise RuntimeError("Stufe A braucht eine Systematic Review ... mit Volltext")

    card = {"slug": "k-1", "title": "K", "topic": "intervalle", "summary": "S", "recommendation": "R", "evidence": "A", "directness": "direct"}
    dlg = CardEditorDialog(window, heading="Test", card=card, sources=[], paper=None, submit=refuse)
    dlg._save()
    assert "Stufe A braucht" in dlg.error.text() and dlg.result() != QDialog.DialogCode.Accepted
    dlg.status.setCurrentIndex(dlg.status.findData("contested"))
    assert not dlg.positions_box.isHidden() or dlg.positions_box.isVisibleTo(dlg)  # Positionen nur bei „Umstritten“


def test_reject_and_watch_flow(window, services, monkeypatch):
    run_research(window)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", True))
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    window.results.reject_candidate()
    assert shown and "Grund" in shown[0] and services.backend.decisions == [(3, "reject", "Automatisch: Andere Population")]  # nichts verworfen ohne Grund
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Nur 8 Teilnehmer", True))
    window.results.reject_candidate()
    settle(window.results)
    assert services.backend.decisions[-1][1:] == ("reject", "Nur 8 Teilnehmer")
    wait_for(lambda: window.results.list.count() == 1)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", True))
    window.results.watch_candidate()
    settle(window.results)
    assert services.backend.decisions[-1][1] == "watch"


# ---------------------------------------------------------- Wissensbasis-Reiter ---


def knowledge_cards():
    base = {"topic": "intervalle", "topic_label": "Intervalle", "summary": "S", "recommendation": "R", "directness": "direct", "applies_to": {},
            "claims": [], "sources": [], "version": 1, "reviewed": "2026-01-01", "review_due": "2027-01-01", "safety": False}
    return [{**base, "slug": "a", "title": "Aktive Karte", "evidence": "A", "status": "active", "review_overdue": False},
            {**base, "slug": "b", "title": "Veraltete Karte", "evidence": "C", "status": "active", "review_overdue": True},
            {**base, "slug": "c", "title": "Umstrittene", "evidence": "B", "status": "contested", "review_overdue": False},
            {**base, "slug": "d", "title": "Stillgelegt", "evidence": "B", "status": "retired", "review_overdue": False},
            {**base, "slug": "e", "title": "Kraft-Karte", "topic": "kraft", "topic_label": "Kraft", "evidence": "B", "status": "active", "review_overdue": False}]


def test_knowledge_tab_filters_edit_retire_history(window, services, monkeypatch):
    services.backend._cards = knowledge_cards()
    tab = window.knowledge
    tab.refresh()
    settle(tab)
    wait_for(lambda: tab.list.count() == 4)
    assert tab.list.count() == 4  # Standardansicht: aktiv und umstritten, stillgelegte fehlen
    tab.overdue.setChecked(True)
    assert tab.list.count() == 1 and "Veraltete Karte" in tab.list.item(0).text() and "Review fällig" in tab.list.item(0).text()
    tab.overdue.setChecked(False)
    tab.topic.setCurrentIndex(tab.topic.findData("kraft"))
    assert tab.list.count() == 1
    tab.topic.setCurrentIndex(0)
    tab.status.setCurrentIndex(tab.status.findData("retired"))
    assert tab.list.count() == 1 and not tab.retire_btn.isEnabled()  # Stillgelegtes laesst sich nicht erneut stilllegen
    tab.status.setCurrentIndex(0)
    tab.list.setCurrentRow(0)

    def fake_exec(self):
        assert self.existing and self.slug.isReadOnly() and not self.review.isHidden() or self.review.isVisibleTo(self)
        self.note.setText("Empfehlung geschärft")
        self._save()
        return 1

    monkeypatch.setattr(CardEditorDialog, "exec", fake_exec)
    tab.edit_card()
    settle(tab)
    slug, body = services.backend.saved[0]
    assert slug == "a" and body["note"] == "Empfehlung geschärft" and body["evidence"] == "A" and "sources" in body

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Überholt", True))
    tab.retire_card()
    assert services.backend.retired == [("a", "Überholt")]
    monkeypatch.setattr(knowledge_tab.QDialog, "exec", lambda self: 0)
    tab.show_history()  # oeffnet den Verlauf ohne Fehler
    tab.refresh()
    settle(tab)


def test_settings_dialog_roundtrip(window):
    from wissens_manager.ui.main_window import SettingsDialog

    dlg = SettingsDialog(window, Config(backend_url="http://x:1", admin_token="geheim", model="opus", parallel=2))
    assert dlg.url.text() == "http://x:1" and dlg.token.text() == "geheim" and dlg.model.currentText() == "opus"
    dlg.url.setText(" http://y:2/ ")
    dlg.parallel.setValue(3)
    v = dlg.values()
    assert v.backend_url == "http://y:2" and v.parallel == 3 and v.claude_path == "claude"


def test_screenshots_of_all_areas(window, services, tmp_path):
    """Haelt die drei Bereiche als Bilder fest (zum Ansehen); sie muessen sich ohne Fehler darstellen lassen."""
    run_research(window)
    services.backend._cards = knowledge_cards()
    window.knowledge.refresh()
    settle(window.knowledge)
    wait_for(lambda: window.knowledge.list.count() > 0)
    out = os.environ.get("WM_SHOT_DIR") or str(tmp_path)
    os.makedirs(out, exist_ok=True)
    for i, name in enumerate(("recherche", "ergebnisse", "wissensbasis")):
        window.tabs.setCurrentIndex(i)
        app.processEvents()
        assert window.grab().save(os.path.join(out, f"{name}.png"))
