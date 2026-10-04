"""Bereich 1: Recherche starten (Thema oder eigene Frage) oder eine einzelne Studie per DOI/PMID auswerten."""

from __future__ import annotations

import datetime as dt
from typing import Callable

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                             QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .. import pipeline, topics
from .core import Services, Task


class ResearchTab(QWidget):
    finished = pyqtSignal()  # Ergebnisse haben sich geaendert

    def __init__(self, get_services: Callable[[], Services]):
        super().__init__()
        self.get_services = get_services
        self._task: Task | None = None
        self._last_stage = ""

        self.topic = QComboBox()
        for key, (label, _) in topics.TOPICS.items():
            self.topic.addItem(label, key)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Optional: eigene Suchanfrage in Europe-PMC-Syntax (ersetzt die Standardanfrage des Themas)")
        self.types = {key: QCheckBox(label) for key, (label, _) in topics.STUDY_TYPES.items()}
        for key, box in self.types.items():
            box.setChecked(key in topics.DEFAULT_STUDY_TYPES)
        self.year = QSpinBox()
        self.year.setRange(1990, dt.date.today().year)
        self.year.setValue(dt.date.today().year - 6)
        self.max = QSpinBox()
        self.max.setRange(1, 100)
        self.max.setValue(self.get_services().cfg.max_papers)

        form = QFormLayout()
        form.addRow("Thema", self.topic)
        form.addRow("Eigene Anfrage", self.query)
        types_row = QHBoxLayout()
        for box in self.types.values():
            types_row.addWidget(box)
        types_row.addStretch()
        form.addRow("Studientypen", types_row)
        nums = QHBoxLayout()
        nums.addWidget(QLabel("Erschienen ab"))
        nums.addWidget(self.year)
        nums.addSpacing(16)
        nums.addWidget(QLabel("Höchstens neue Studien"))
        nums.addWidget(self.max)
        nums.addStretch()
        form.addRow("Umfang", nums)

        self.start_btn = QPushButton("Recherche starten")
        self.start_btn.setObjectName("primary")
        self.cancel_btn = QPushButton("Abbrechen")
        self.cancel_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start)
        self.cancel_btn.clicked.connect(self.cancel)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.cancel_btn)
        buttons.addStretch()

        group = QGroupBox("Neue Recherche")
        gl = QVBoxLayout(group)
        gl.addLayout(form)
        gl.addLayout(buttons)

        self.ident = QLineEdit()
        self.ident.setPlaceholderText("DOI oder PMID einfügen, z. B. 10.1111/sms.12345 oder 19910006")
        self.ident_btn = QPushButton("Studie auswerten")
        self.ident_btn.clicked.connect(self.analyze_one)
        one = QGroupBox("Einzelne Studie auswerten (Thema oben wählen)")
        ol = QHBoxLayout(one)
        ol.addWidget(self.ident, 1)
        ol.addWidget(self.ident_btn)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.hint = QLabel("Die KI-Auswertung läuft über Dein Claude-Abo (Programm „claude“). Große Recherchen können die Abo-Grenze erreichen "
                           "und pausieren; bereits Ausgewertetes bleibt erhalten.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(group)
        lay.addWidget(one)
        lay.addWidget(self.bar)
        lay.addWidget(self.log, 1)
        lay.addWidget(self.hint)

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

    def start(self) -> None:
        s = self.get_services()
        opts = pipeline.ResearchOptions(
            topic=self.topic.currentData(), free_text=self.query.text(),
            study_types=tuple(k for k, b in self.types.items() if b.isChecked()), year_from=self.year.value(),
            max_papers=self.max.value(), batch_size=s.cfg.batch_size, parallel=s.cfg.parallel)
        try:
            topics.build_query(opts.topic, opts.free_text, opts.study_types, opts.year_from)
        except ValueError as e:
            QMessageBox.warning(self, "Recherche", str(e))
            return
        self.log.appendPlainText(f"— Recherche „{self.topic.currentText()}“ —")
        self._run(lambda progress, cancelled: pipeline.run_research(
            opts, backend=s.backend, ai=s.ai, epmc_http=s.epmc_http, crossref_http=s.crossref_http, progress=progress, cancelled=cancelled))

    def analyze_one(self) -> None:
        ident = self.ident.text().strip()
        if not ident:
            QMessageBox.information(self, "Studie auswerten", "Bitte eine DOI oder PMID eingeben.")
            return
        s = self.get_services()
        topic = self.topic.currentData()
        self.log.appendPlainText(f"— Einzelne Studie {ident} —")
        self._run(lambda progress, cancelled: pipeline.analyze_identifier(
            ident, topic, backend=s.backend, ai=s.ai, epmc_http=s.epmc_http, crossref_http=s.crossref_http, progress=progress))

    def cancel(self) -> None:
        if self._task and self._task.isRunning():
            self._task.requestInterruption()
            self.log.appendPlainText("Abbruch angefordert, das laufende Paket wird noch fertig ausgewertet ...")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, stage: str, done: int, total: int, message: str) -> None:
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(done)
        if stage != self._last_stage or done == total:
            self.log.appendPlainText(message)
            self._last_stage = stage

    def _on_done(self, summary: pipeline.RunSummary) -> None:
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
