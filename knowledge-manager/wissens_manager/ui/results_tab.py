"""Bereich 2: Ergebnisse mit KI-Zusammenfassung ansehen und entscheiden (aufnehmen, Watchlist, verwerfen)."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSplitter,
                             QTextBrowser, QVBoxLayout, QWidget)

from .. import topics
from ..backend import BackendError
from .card_editor import CardEditorDialog
from .core import Services, Task
from .render import STATUS_LABELS, candidate_html, candidate_title, evidence_cap

_LETTERS = "ABC"


def capped_evidence(suggestion: str | None, basis: str | None) -> str:
    """Evidenzvorschlag der KI, begrenzt auf das, was die Quellenbasis hergibt (nur Abstract: B)."""
    s = suggestion if suggestion in tuple(_LETTERS) else "C"
    cap = evidence_cap(basis)
    return cap if _LETTERS.index(s) < _LETTERS.index(cap) else s


class ResultsTab(QWidget):
    changed = pyqtSignal()  # eine Karte wurde angelegt oder geaendert

    def __init__(self, get_services: Callable[[], Services]):
        super().__init__()
        self.get_services = get_services
        self.items: list[dict] = []
        self._task: Task | None = None

        self.status = QComboBox()
        for key in ("pending", "watch", "accepted", "rejected"):
            self.status.addItem(STATUS_LABELS[key], key)
        self.topic = QComboBox()
        self.topic.addItem("Alle Themen", None)
        for key, (label, _) in topics.TOPICS.items():
            self.topic.addItem(label, key)
        self.refresh_btn = QPushButton("Aktualisieren")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        top = QHBoxLayout()
        for w in (QLabel("Status"), self.status, QLabel("Thema"), self.topic, self.refresh_btn, self.count):
            top.addWidget(w)
        top.addStretch()

        self.list = QListWidget()
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.list)
        split.addWidget(self.detail)
        split.setSizes([360, 640])

        self.accept_btn = QPushButton("Aufnehmen …")
        self.accept_btn.setObjectName("primary")
        self.watch_btn = QPushButton("Auf die Watchlist")
        self.reject_btn = QPushButton("Verwerfen …")
        self.reject_btn.setObjectName("danger")
        self.open_btn = QPushButton("Studie im Browser öffnen")
        actions = QHBoxLayout()
        for b in (self.accept_btn, self.watch_btn, self.reject_btn, self.open_btn):
            actions.addWidget(b)
        actions.addStretch()

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(actions)

        self.status.currentIndexChanged.connect(self.refresh)
        self.topic.currentIndexChanged.connect(self._populate)
        self.refresh_btn.clicked.connect(self.refresh)
        self.list.currentRowChanged.connect(self._show)
        self.accept_btn.clicked.connect(self.accept_candidate)
        self.watch_btn.clicked.connect(self.watch_candidate)
        self.reject_btn.clicked.connect(self.reject_candidate)
        self.open_btn.clicked.connect(self.open_paper)
        self._update_buttons()

    # --------------------------------------------------------------- Laden ---

    def refresh(self) -> None:
        s = self.get_services()
        status = self.status.currentData()
        self.count.setText("Lade ...")
        self._task = Task(lambda progress, cancelled: s.backend.candidates(status), self)
        self._task.done.connect(self._loaded)
        self._task.failed.connect(lambda m: (self.count.setText(""), self.detail.setPlainText(f"Fehler: {m}")))
        self._task.start()

    def _loaded(self, items: list[dict]) -> None:
        self.items = sorted(items, key=lambda c: -c["id"])
        self._populate()

    def _populate(self) -> None:
        topic = self.topic.currentData()
        shown = [c for c in self.items if topic is None or c["topic"] == topic]
        self._shown = shown
        self.list.blockSignals(True)
        self.list.clear()
        for c in shown:
            self.list.addItem(QListWidgetItem(candidate_title(c)))
        self.list.blockSignals(False)
        self.count.setText(f"{len(shown)} Einträge")
        if shown:
            self.list.setCurrentRow(0)
            self._show(0)
        else:
            self.detail.setHtml("<p style='color:#94a3b8'>Keine Einträge. Starte eine Recherche oder wechsle den Status.</p>")
            self._update_buttons()

    def current(self) -> dict | None:
        r = self.list.currentRow()
        shown = getattr(self, "_shown", [])
        return shown[r] if 0 <= r < len(shown) else None

    def _show(self, _row: int) -> None:
        c = self.current()
        self.detail.setHtml(candidate_html(c) if c else "")
        self._update_buttons()

    def _update_buttons(self) -> None:
        c = self.current()
        pending = bool(c and c["status"] == "pending")
        irrelevant = bool(c and (c["analysis"].get("ai") or {}).get("suggested_action") == "irrelevant")
        self.accept_btn.setEnabled(pending and not irrelevant)
        self.watch_btn.setEnabled(pending)
        self.reject_btn.setEnabled(pending)
        self.open_btn.setEnabled(bool(c and (c["analysis"].get("paper") or {}).get("url")))

    # --------------------------------------------------------- Entscheidungen ---

    def _decide(self, action: str, note: str | None) -> None:
        c = self.current()
        try:
            self.get_services().backend.decide(c["id"], action, note)
        except BackendError as e:
            QMessageBox.warning(self, "Entscheidung", str(e))
            return
        self.refresh()

    def watch_candidate(self) -> None:
        note, ok = QInputDialog.getText(self, "Watchlist", "Notiz (optional):")
        if ok:
            self._decide("watch", note.strip() or None)

    def reject_candidate(self) -> None:
        note, ok = QInputDialog.getText(self, "Verwerfen", "Grund (wird gespeichert, die Studie wird nicht erneut vorgeschlagen):")
        if not ok:
            return
        if not note.strip():
            QMessageBox.information(self, "Verwerfen", "Bitte einen kurzen Grund angeben.")
            return
        self._decide("reject", note.strip())

    def open_paper(self) -> None:
        c = self.current()
        if c and (url := (c["analysis"].get("paper") or {}).get("url")):
            QDesktopServices.openUrl(QUrl(url))

    def accept_candidate(self) -> None:
        c = self.current()
        s = self.get_services()
        a = c["analysis"]
        ai, paper, suggested = a.get("ai") or {}, a.get("paper") or {}, a.get("suggested_source")
        if not suggested:
            QMessageBox.warning(self, "Aufnehmen", "Zu diesem Eintrag gibt es keinen Quellenvorschlag.")
            return
        key = suggested["key"]
        quote = (ai.get("quotes") or [""])[0]
        flags_note = ""
        try:
            if ai.get("suggested_action") in ("supports", "contradicts") and ai.get("target_card"):
                # Studie ergaenzt eine vorhandene Karte: neue Version dieser Karte, Quelle und Aussage kommen dazu
                card = s.backend.card(ai["target_card"])
                card["claims"] = [*card.get("claims", []), {"text": ai.get("finding") or ai.get("summary", ""), "quote": quote, "source_key": key}]
                sources = [*card.get("sources", []), suggested]
                existing, heading = True, f"Karte ergänzen: {card['title']}"
                flags_note = "contradicts" if ai.get("suggested_action") == "contradicts" else ""
            else:
                draft = ai.get("card_draft") or {}
                card = {**draft, "topic": c["topic"], "status": "active", "directness": ai.get("directness", "indirect"),
                        "evidence": capped_evidence(ai.get("evidence_suggestion"), suggested.get("basis")),
                        "claims": [{**cl, "source_key": key} for cl in draft.get("claims", [])]}
                if not card["claims"] and quote:
                    card["claims"] = [{"text": ai.get("finding") or ai.get("summary", ""), "quote": quote, "source_key": key}]
                sources = [suggested]
                existing, heading = False, f"Neue Karte: {c['title']}"
        except BackendError as e:
            QMessageBox.warning(self, "Aufnehmen", str(e))
            return
        dlg = CardEditorDialog(self, heading=heading, card=card, sources=sources, paper=paper, existing=existing,
                               submit=lambda body, srcs, note: s.backend.decide(c["id"], "accept", note or None, body, srcs))
        if flags_note == "contradicts":
            dlg.error.setText("Die Studie widerspricht der Karte: Prüfe, ob der Status „Umstritten“ mit zwei Positionen passt.")
        if dlg.exec():
            self.refresh()
            self.changed.emit()
