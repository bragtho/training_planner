"""Bereich 3: Wissensbasis durchsuchen, Karten bearbeiten, stilllegen, Verlauf ansehen und sichern."""

from __future__ import annotations

import json
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton,
                             QSplitter, QVBoxLayout, QWidget)

from .. import topics
from ..backend import BackendError
from .card_editor import CardEditorDialog
from .core import Services, Task
from .detail import CARD_STATUS_COLORS, card_widgets
from .render import CARD_STATUS_LABELS
from .widgets import icon_button, EVIDENCE_COLORS, RED, SLATE, Card, CardList, DetailView, ListItem, Toolbar, action_bar, label


class KnowledgeTab(QWidget):
    def __init__(self, get_services: Callable[[], Services]):
        super().__init__()
        self.get_services = get_services
        self.cards: list[dict] = []
        self._shown: list[dict] = []
        self._task: Task | None = None

        self.topic = QComboBox()
        self.topic.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.topic.setMinimumContentsLength(12)
        self.topic.addItem("Alle Themen", None)
        for key, (label_, _) in topics.TOPICS.items():
            self.topic.addItem(label_, key)
        self.status = QComboBox()
        self.status.setMinimumWidth(200)
        self.status.addItem("Aktiv und umstritten", "live")
        for key in ("active", "contested", "watch", "retired"):
            self.status.addItem(CARD_STATUS_LABELS[key], key)
        self.status.addItem("Alle", None)
        self.overdue = QCheckBox("Nur Überprüfung fällig")
        self.refresh_btn = icon_button("refresh", "Aktualisieren")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        top = Toolbar(self.topic, self.status, self.overdue, self.refresh_btn, right=self.count)

        self.list = CardList()
        self.list.setMinimumWidth(320)
        self.detail = DetailView()
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(24)  # Abstand zwischen Liste und Detail (Stylesheet allein greift nicht auf jedem System)
        split.addWidget(self.list)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([430, 700])

        self.new_btn = QPushButton("Neue Karte …")
        self.new_btn.setObjectName("primary")
        self.edit_btn = QPushButton("Bearbeiten …")
        self.retire_btn = QPushButton("Stilllegen …")
        self.retire_btn.setObjectName("danger")
        self.history_btn = QPushButton("Verlauf")
        self.export_btn = QPushButton("Sicherung exportieren …")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(top)
        lay.addWidget(split, 1)
        lay.addWidget(action_bar(self.new_btn, self.edit_btn, self.retire_btn, self.history_btn, self.export_btn))

        self.topic.currentIndexChanged.connect(self._populate)
        self.status.currentIndexChanged.connect(self._populate)
        self.overdue.toggled.connect(self._populate)
        self.refresh_btn.clicked.connect(self.refresh)
        self.list.currentRowChanged.connect(self._show)
        self.new_btn.clicked.connect(self.new_card)
        self.edit_btn.clicked.connect(self.edit_card)
        self.retire_btn.clicked.connect(self.retire_card)
        self.history_btn.clicked.connect(self.show_history)
        self.export_btn.clicked.connect(self.export_all)
        self._update_buttons()

    def refresh(self) -> None:
        s = self.get_services()
        self.count.setText("Lade ...")
        self._task = Task(lambda progress, cancelled: s.backend.cards(), self)
        self._task.done.connect(self._loaded)
        self._task.failed.connect(lambda m: (self.count.setText(""), self.detail.show_message(m, "Fehler beim Laden")))
        self._task.start()

    def _loaded(self, cards: list[dict]) -> None:
        self.cards = cards
        self._populate()

    def _populate(self) -> None:
        topic, status = self.topic.currentData(), self.status.currentData()
        shown = [c for c in self.cards
                 if (topic is None or c["topic"] == topic)
                 and (status is None or (c["status"] in ("active", "contested") if status == "live" else c["status"] == status))
                 and (not self.overdue.isChecked() or c.get("review_overdue"))]
        self._shown = shown
        self.list.blockSignals(True)
        self.list.clear()
        for c in shown:
            flag = " ⚠ Review fällig" if c.get("review_overdue") else ""
            status = CARD_STATUS_LABELS.get(c["status"], c["status"])
            pills = [(status, CARD_STATUS_COLORS.get(c["status"], SLATE))]
            if c.get("review_overdue"):
                pills.append(("Review fällig", RED))
            if c.get("safety"):
                pills.append(("sicherheitsrelevant", RED))
            self.list.add(f"[{c['evidence']}] {c['title']}\n{c['topic_label']} · {status}{flag}",
                          ListItem(title=c["title"], meta=c.get("topic_label") or "", pills=pills,
                                   badge=(c["evidence"], EVIDENCE_COLORS.get(c["evidence"], SLATE))))
        self.list.blockSignals(False)
        self.count.setText(f"{len(shown)} von {len(self.cards)} Karten")
        if shown:
            self.list.setCurrentRow(0)
            self._show(0)
        else:
            self.detail.show_message("Keine Karten in dieser Ansicht. Ändere die Filter oder lege eine neue Karte an.")
            self._update_buttons()

    def current(self) -> dict | None:
        r = self.list.currentRow()
        return self._shown[r] if 0 <= r < len(self._shown) else None

    def _show(self, _row: int) -> None:
        c = self.current()
        if c:
            self.detail.set_widgets(card_widgets(c))
        else:
            self.detail.clear()
        self._update_buttons()

    def _update_buttons(self) -> None:
        c = self.current()
        self.edit_btn.setEnabled(bool(c))
        self.retire_btn.setEnabled(bool(c and c["status"] != "retired"))
        self.history_btn.setEnabled(bool(c))

    # ------------------------------------------------------------- Aktionen ---

    def _edit(self, card: dict, sources: list[dict], existing: bool, heading: str) -> None:
        s = self.get_services()

        def submit(body: dict, srcs: list[dict], note: str) -> None:
            s.backend.put_card(body["slug"], {**body, "sources": srcs, "note": note or None})

        if CardEditorDialog(self, heading=heading, card=card, sources=sources, paper=None, existing=existing, submit=submit).exec():
            self.refresh()

    def new_card(self) -> None:
        self._edit({"status": "active", "evidence": "D", "directness": "extrapolated"}, [], False, "Neue Karte (z. B. Expertenpraxis, Stufe D)")

    def edit_card(self) -> None:
        c = self.current()
        if c:
            self._edit(c, c.get("sources", []), True, f"Karte bearbeiten: {c['title']}")

    def retire_card(self) -> None:
        c = self.current()
        if not c:
            return
        note, ok = QInputDialog.getText(self, "Stilllegen", f"„{c['title']}“ stilllegen. Der Coach nutzt sie danach nicht mehr.\nGrund:")
        if not ok:
            return
        try:
            self.get_services().backend.retire(c["slug"], note.strip() or None)
        except BackendError as e:
            QMessageBox.warning(self, "Stilllegen", str(e))
            return
        self.refresh()

    def show_history(self) -> None:
        c = self.current()
        if not c:
            return
        try:
            history = self.get_services().backend.history(c["slug"])
        except BackendError as e:
            QMessageBox.warning(self, "Verlauf", str(e))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Verlauf: {c['title']}")
        dlg.resize(760, 640)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)
        v.addWidget(label(f"Verlauf: {c['title']}", "h2"))
        view = DetailView()
        actions = {"created": "angelegt", "updated": "geändert", "retired": "stillgelegt"}
        cards = []
        for h in history:
            card = Card(f"Version {h['version']} · {actions.get(h['action'], h['action'])}",
                        h["changed_at"][:16].replace("T", " "))
            if h.get("note"):
                card.add(label(h["note"], "muted", selectable=True))
            rec = (h.get("snapshot") or {}).get("recommendation")
            if rec:
                card.add(label(rec, "body", selectable=True))
            cards.append(card)
        if cards:
            view.set_widgets(cards)
        else:
            view.show_message("Kein Verlauf.")
        v.addWidget(view, 1)
        close = QPushButton("Schließen")
        close.clicked.connect(dlg.accept)
        v.addWidget(action_bar(close))
        dlg.exec()

    def export_all(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Sicherung speichern", "wissensbasis-sicherung.json", "JSON (*.json)")
        if not path:
            return
        try:
            data = self.get_services().backend.export()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (BackendError, OSError) as e:
            QMessageBox.warning(self, "Export", str(e))
            return
        QMessageBox.information(self, "Export", f"Gespeichert: {path}")
