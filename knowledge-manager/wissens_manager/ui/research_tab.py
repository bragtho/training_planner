"""Bereich 1: Recherche per Freitext starten (die KI uebersetzt die Frage in Suchanfragen) oder eine einzelne Studie per DOI/PMID auswerten."""

from __future__ import annotations

import datetime as dt
from typing import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                             QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import pipeline, topics
from .core import Services, Task
from .widgets import Card, action_bar, label, labeled


class ResearchTab(QWidget):
    finished = pyqtSignal()  # Ergebnisse haben sich geaendert

    def __init__(self, get_services: Callable[[], Services]):
        super().__init__()
        self.get_services = get_services
        self._task: Task | None = None
        self._last_stage = ""
        self.new_after_id = 0  # Ergebnis des letzten Laufs: Kandidaten mit hoeherer ID sind neu

        self.request = QPlainTextEdit()
        self.request.setPlaceholderText("Wonach soll gesucht werden? Beschreibe es in eigenen Worten, z. B. „Finde Studien zum Thema "
                                        "Makrozyklen im Radsport“ oder „Wie wirkt Krafttraining auf die Sprintleistung von Radfahrern?“")
        self.request.setMinimumHeight(88)
        self.request.setMaximumHeight(120)
        self.preset = QComboBox()
        self.preset.addItem("Vorschlag einfügen …", None)
        for key, (name, _) in topics.TOPICS.items():
            if key != "sonstiges":
                self.preset.addItem(name, name)
        self.preset.activated.connect(self._insert_preset)
        self.preset.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.preset.setMinimumContentsLength(16)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Optional, für Kenner: fertige Europe-PMC-Suchanfrage (ersetzt die Übersetzung durch die KI)")
        self.types = {key: QCheckBox(name) for key, (name, _) in topics.STUDY_TYPES.items()}
        for key, box in self.types.items():
            box.setChecked(key in topics.DEFAULT_STUDY_TYPES)
        self.year = QSpinBox()
        self.year.setRange(1990, dt.date.today().year)
        self.year.setValue(dt.date.today().year - 6)
        self.max = QSpinBox()
        self.max.setRange(1, 100)
        self.max.setValue(self.get_services().cfg.max_papers)

        self.year.setMinimumWidth(110)
        self.max.setMinimumWidth(110)

        self.start_btn = QPushButton("Recherche starten")
        self.start_btn.setObjectName("primary")
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn.clicked.connect(self.cancel)

        # Karte 1: neue Recherche
        new_card = Card("Neue Recherche", "Beschreibe in eigenen Worten, was Du wissen willst. Die KI übersetzt die Frage in Suchanfragen "
                                          "für Europe PMC und bewertet die gefundenen Studien.", spacing=14)
        ask = QHBoxLayout()
        ask.setSpacing(12)
        ask.addWidget(labeled("Frage", self.request), 1)
        side = QVBoxLayout()
        side.setSpacing(4)
        side.addWidget(label("Beispiel", "caption", wrap=False))
        side.addWidget(self.preset)
        side.addStretch(1)
        ask.addLayout(side)
        new_card.body.addLayout(ask)
        types_row = QHBoxLayout()
        types_row.setSpacing(18)
        for box in self.types.values():
            types_row.addWidget(box)
        types_row.addStretch()
        types_w = QWidget()
        types_w.setObjectName("plain")
        types_w.setLayout(types_row)
        new_card.add(labeled("Studientypen", types_w))
        opts = QHBoxLayout()
        opts.setSpacing(16)
        opts.addWidget(labeled("Erschienen ab", self.year))
        opts.addWidget(labeled("Höchstens neue Studien", self.max))
        opts.addStretch(1)
        new_card.body.addLayout(opts)
        new_card.add(labeled("Erweitert (optional)", self.query))
        new_card.add(action_bar(self.start_btn, self.cancel_btn))

        # Karte 2: einzelne Studie
        self.ident = QLineEdit()
        self.ident.setPlaceholderText("DOI oder PMID einfügen, z. B. 10.1111/sms.12345 oder 19910006")
        self.ident_btn = QPushButton("Studie auswerten")
        self.ident_btn.clicked.connect(self.analyze_one)
        one = Card("Einzelne Studie auswerten", "Die Frage oben dient als Zusammenhang für die Bewertung.", spacing=12)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.ident, 1)
        row.addWidget(self.ident_btn)
        one.body.addLayout(row)

        # Karte 3: Fortschritt und Protokoll
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(140)
        self.hint = label("Die KI-Auswertung läuft über Dein Claude-Abo (Programm „claude“). Große Recherchen können die Abo-Grenze "
                          "erreichen und pausieren; bereits Ausgewertetes bleibt erhalten.", "small")
        prog = Card("Fortschritt", spacing=12)
        prog.add(self.bar)
        prog.body.addWidget(self.log, 1)
        prog.add(self.hint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(16)
        lay.addWidget(new_card)
        lay.addWidget(one)
        lay.addWidget(prog, 1)

    # --------------------------------------------------------------- Ablauf ---

    def _busy(self, busy: bool) -> None:
        self.start_btn.setEnabled(not busy)
        self.ident_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)

    def _run(self, fn) -> None:
        self._task = Task(fn, self)
        self._task.progress.connect(self._on_progress)
        self._task.done.connect(self._on_done)
        self._task.failed.connect(self._on_failed)
        self._task.finished.connect(lambda: self._busy(False))
        self._busy(True)
        self._last_stage = ""
        self.bar.setRange(0, 0)  # unbestimmt, bis der erste Fortschritt kommt
        self._task.start()

    def _insert_preset(self, index: int) -> None:
        label = self.preset.itemData(index)
        if label:
            self.request.setPlainText(f"Finde Studien zum Thema {label} im Radsport")
        self.preset.setCurrentIndex(0)

    def start(self) -> None:
        s = self.get_services()
        request = self.request.toPlainText().strip()
        raw = self.query.text().strip()
        if not request and not raw:
            QMessageBox.warning(self, "Recherche", "Bitte beschreibe, wonach gesucht werden soll (oder gib unter „Erweitert“ eine Suchanfrage an).")
            return
        opts = pipeline.ResearchOptions(
            request=request, free_text=raw, study_types=tuple(k for k, b in self.types.items() if b.isChecked()),
            year_from=self.year.value(), max_papers=self.max.value(), batch_size=s.cfg.batch_size, parallel=s.cfg.parallel)
        self.log.appendPlainText(f"— Recherche: {(request or raw)[:120]} —")

        def job(progress, cancelled):
            before = max((c["id"] for c in s.backend.candidates()), default=0)
            summary = pipeline.run_research(opts, backend=s.backend, ai=s.ai, epmc_http=s.epmc_http, crossref_http=s.crossref_http,
                                            progress=progress, cancelled=cancelled)
            summary.new_after_id = before
            return summary

        self._run(job)

    def analyze_one(self) -> None:
        ident = self.ident.text().strip()
        if not ident:
            QMessageBox.information(self, "Studie auswerten", "Bitte eine DOI oder PMID eingeben.")
            return
        s = self.get_services()
        focus = self.request.toPlainText().strip()
        self.log.appendPlainText(f"— Einzelne Studie {ident} —")

        def job(progress, cancelled):
            before = max((c["id"] for c in s.backend.candidates()), default=0)
            summary = pipeline.analyze_identifier(ident, backend=s.backend, ai=s.ai, epmc_http=s.epmc_http, crossref_http=s.crossref_http,
                                                  progress=progress, focus=focus)
            summary.new_after_id = before
            return summary

        self._run(job)

    def cancel(self) -> None:
        if self._task and self._task.isRunning():
            self._task.requestInterruption()
            self.log.appendPlainText("Abbruch angefordert, das laufende Paket wird noch fertig ausgewertet ...")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, done: int, total: int, message: str) -> None:
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(done)
        if stage != self._last_stage or done == total or stage == "planen":
            self.log.appendPlainText(message)
            self._last_stage = stage

    def _on_done(self, summary: pipeline.RunSummary) -> None:
        self.new_after_id = summary.new_after_id
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        self.log.appendPlainText("Fertig: " + summary.text())
        for err in summary.errors:
            self.log.appendPlainText(f"  Hinweis: {err}")
        if summary.ai_calls:
            self.log.appendPlainText(f"  KI-Aufrufe: {summary.ai_calls} (Abo)")
        self.finished.emit()

    def _on_failed(self, message: str) -> None:
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.log.appendPlainText(f"Fehler: {message}")
