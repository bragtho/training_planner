"""Editor fuer eine Wissenskarte samt Quellen: Aufnehmen eines Kandidaten oder Bearbeiten einer vorhandenen Karte.

Der Editor prueft lokal nur, was das Backend nicht kann (Belegzitat steht im Abstract). Alle anderen Regeln
(Evidenzstufen, Pflichtfelder, zurueckgezogene Quellen ...) prueft das Backend; seine Meldung erscheint im Dialog.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import topics, verify
from .render import CARD_STATUS_LABELS, DESIGN_LABELS, DIRECTNESS_LABELS, EVIDENCE_LABELS
from .widgets import Card, DialogFrame, labeled, plain

POPULATIONS = [("elite", "Elite"), ("trained", "Trainierte"), ("recreational", "Freizeit")]
SEXES = [("all", "alle Geschlechter"), ("female", "Frauen"), ("male", "Männer")]
BASES = [("abstract", "Nur Abstract geprüft"), ("fulltext", "Volltext selbst gelesen")]
SOURCE_COLS = ["Schlüssel", "Autoren", "Jahr", "Titel", "Journal", "DOI", "PMID", "Design", "n", "Population", "Basis"]


def _combo(options: list[tuple[str, str]], current: str | None) -> QComboBox:
    box = QComboBox()
    for value, label in options:
        box.addItem(label, value)
    i = box.findData(current)
    box.setCurrentIndex(i if i >= 0 else 0)
    return box


class CardEditorDialog(QDialog):
    def __init__(self, parent, *, heading: str, card: dict, sources: list[dict], paper: dict | None,
                 submit: Callable[[dict, list[dict], str], None], existing: bool = False):
        super().__init__(parent)
        self.setWindowTitle(heading)
        self.resize(1000, 860)
        self.paper = paper
        self.submit = submit
        self.existing = existing
        self._card = card
        # Rueckzugsstatus der Quellen bleibt erhalten (Tabelle zeigt ihn nicht); Zuordnung ueber DOI oder Schluessel
        self._flags: dict[str, dict] = {}
        for s in sources:
            f = {"retracted": bool(s.get("retracted")), "retraction_checked": s.get("retraction_checked")}
            self._flags[(s.get("doi") or "").lower() or s.get("key", "")] = f
            self._flags[s.get("key", "")] = f

        self.resize(1100, 900)
        frame = DialogFrame(self, heading.split(": ", 1)[0], heading.split(": ", 1)[1] if ": " in heading else None)
        add = frame.add

        # --- Grunddaten
        self.slug = QLineEdit(card.get("slug", ""))
        self.slug.setReadOnly(existing)  # der Schluessel einer vorhandenen Karte bleibt
        self.title = QLineEdit(card.get("title", ""))
        self.topic = _combo([(k, v[0]) for k, v in topics.TOPICS.items()], card.get("topic"))
        self.status = _combo([(k, CARD_STATUS_LABELS[k]) for k in ("active", "contested", "watch")], card.get("status", "active"))
        self.evidence = _combo(list(EVIDENCE_LABELS.items()), card.get("evidence", "C"))
        self.directness = _combo(list(DIRECTNESS_LABELS.items()), card.get("directness", "indirect"))
        self.safety = QCheckBox("Sicherheitsrelevant (Energiemangel, Ernährung, Zyklus …): braucht Stufe A mit Konsens-Statement")
        self.safety.setChecked(bool(card.get("safety")))
        self.tags = QLineEdit(", ".join(card.get("tags") or []))
        self.tags.setPlaceholderText("Komma-getrennt, z. B. vo2max, hiit")
        base = Card("Grunddaten", spacing=14)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)
        grid.addWidget(labeled("Titel", self.title), 0, 0, 1, 2)
        grid.addWidget(labeled("Schlüssel (Slug)", self.slug), 1, 0)
        grid.addWidget(labeled("Stichwörter", self.tags), 1, 1)
        grid.addWidget(labeled("Thema", self.topic), 2, 0)
        grid.addWidget(labeled("Status", self.status), 2, 1)
        grid.addWidget(labeled("Evidenzstufe", self.evidence), 3, 0)
        grid.addWidget(labeled("Direktheit", self.directness), 3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        base.body.addLayout(grid)
        base.add(self.safety)
        self.cap_hint = QLabel()
        self.cap_hint.setObjectName("small")
        self.cap_hint.setWordWrap(True)
        base.add(self.cap_hint)
        add(base)

        # --- Texte
        self.summary = self._text(card.get("summary", ""), 76)
        self.recommendation = self._text(card.get("recommendation", ""), 100)
        self.caveats = self._text(card.get("caveats") or "", 76)
        texts = Card("Inhalt", "Was der Coach liest: kurze Einordnung, bedingte Empfehlung und Grenzen.", spacing=14)
        texts.add(labeled("Kurz gesagt (höchstens 400 Zeichen)", self.summary))
        texts.add(labeled("Empfehlung als „Wenn …, dann …“ (höchstens 800 Zeichen)", self.recommendation))
        texts.add(labeled("Grenzen (höchstens 800 Zeichen)", self.caveats))
        add(texts)

        # --- Gilt fuer
        ap = card.get("applies_to") or {}
        self.pops = {k: QCheckBox(label) for k, label in POPULATIONS}
        for k, box in self.pops.items():
            box.setChecked(k in (ap.get("population") or []))
        self.sex = _combo(SEXES, ap.get("sex", "all"))
        self.age = QLineEdit(ap.get("age") or "")
        self.age.setPlaceholderText("z. B. 18-45")
        pops_row = QHBoxLayout()
        pops_row.setSpacing(18)
        for box in self.pops.values():
            pops_row.addWidget(box)
        pops_row.addStretch(1)
        pops_w = plain(QWidget())
        pops_w.setLayout(pops_row)
        applies = Card("Gilt für", "Population der Studien, auf die sich die Karte stützt.", spacing=14)
        arow = QHBoxLayout()
        arow.setSpacing(16)
        arow.addWidget(labeled("Leistungsniveau", pops_w), 2)
        arow.addWidget(labeled("Geschlecht", self.sex), 1)
        arow.addWidget(labeled("Alter", self.age), 1)
        applies.body.addLayout(arow)
        add(applies)

        # --- Quellen
        self.sources_table = QTableWidget(0, len(SOURCE_COLS))
        self.sources_table.setHorizontalHeaderLabels(SOURCE_COLS)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.sources_table.setMinimumHeight(140)
        for col, width in enumerate((130, 170, 70, 280, 170, 180, 100, 180, 60, 190, 200)):
            self.sources_table.setColumnWidth(col, width)
        for s in sources:
            self._add_source(s)
        self.sources_table.cellChanged.connect(lambda *_: self._sources_changed())
        add(self._with_buttons("Quellen", self.sources_table, self._add_empty_source,
                               "Basis „Volltext selbst gelesen“ nur wählen, wenn Du den Volltext geprüft hast."))

        # --- Belegte Aussagen
        self.claims_table = QTableWidget(0, 4)
        self.claims_table.setHorizontalHeaderLabels(["Aussage (eigene Worte)", "Belegzitat (wörtlich, ≤ 25 Wörter)", "Quelle", "Prüfung"])
        self.claims_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.claims_table.setMinimumHeight(160)
        self.claims_table.setWordWrap(True)
        for c in card.get("claims") or []:
            self._add_claim(c.get("text", ""), c.get("quote", ""), c.get("source_key", ""))
        self.claims_table.cellChanged.connect(lambda *_: self._refresh_checks())
        add(self._with_buttons("Belegte Aussagen", self.claims_table, lambda: self._add_claim(),
                               "Jede Aussage braucht ein wörtliches Zitat aus der Quelle und den Quellenschlüssel."))

        # --- Positionen (umstritten)
        self.positions_table = QTableWidget(0, 3)
        self.positions_table.setHorizontalHeaderLabels(["Position", "Kurzbeschreibung", "Quellenschlüssel (Komma)"])
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.positions_table.setMinimumHeight(110)
        for p in card.get("positions") or []:
            self._add_position(p.get("label", ""), p.get("summary", ""), ", ".join(p.get("source_keys") or []))
        self.positions_box = self._with_buttons("Positionen", self.positions_table, lambda: self._add_position(),
                                                "Nur bei Status „Umstritten“: mindestens zwei Lager mit Quellen.")
        add(self.positions_box)
        self.status.currentIndexChanged.connect(self._status_changed)

        # --- Abschluss: Notiz, Review
        self.note = QLineEdit()
        self.note.setPlaceholderText("Erscheint im Verlauf der Karte")
        self.review = QCheckBox("Als heute geprüft markieren (nächste Überprüfung in 12 Monaten)")
        self.review.setChecked(True)
        self.review.setVisible(existing)
        end = Card("Abschluss", spacing=14)
        end.add(labeled("Notiz zur Entscheidung oder Änderung", self.note))
        end.add(self.review)
        add(end)

        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        save = QPushButton("Speichern")
        save.setObjectName("primary")
        cancel = QPushButton("Abbrechen")
        save.clicked.connect(self._save)
        cancel.clicked.connect(self.reject)
        frame.footer.addWidget(self.error, 1)
        frame.footer.addWidget(cancel)
        frame.footer.addWidget(save)
        self._status_changed()
        self._sources_changed()

    # ---------------------------------------------------------- Aufbau-Helfer ---

    @staticmethod
    def _text(value: str, height: int) -> QPlainTextEdit:
        box = QPlainTextEdit(value)
        box.setFixedHeight(height)
        return box

    def _with_buttons(self, title: str, table: QTableWidget, add: Callable[[], None], subtitle: str | None = None) -> Card:
        box = Card(title, subtitle, spacing=12)
        box.add(table)
        row = QHBoxLayout()
        row.setSpacing(10)
        plus = QPushButton("Zeile hinzufügen")
        minus = QPushButton("Markierte Zeile entfernen")
        plus.clicked.connect(add)
        minus.clicked.connect(lambda: self._remove_row(table))
        row.addWidget(plus)
        row.addWidget(minus)
        row.addStretch()
        box.body.addLayout(row)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        return box

    def _remove_row(self, table: QTableWidget) -> None:
        r = table.currentRow()
        if r >= 0:
            table.removeRow(r)
            self._sources_changed() if table is self.sources_table else self._refresh_checks()

    def _add_source(self, s: dict) -> None:
        t = self.sources_table
        t.blockSignals(True)
        r = t.rowCount()
        t.insertRow(r)
        values = [s.get("key", ""), s.get("authors", ""), str(s.get("year") or ""), s.get("title", ""), s.get("journal") or "",
                  s.get("doi") or "", s.get("pmid") or "", None, "" if s.get("sample_n") is None else str(s.get("sample_n")),
                  s.get("population") or "", None]
        for c, v in enumerate(values):
            if v is not None:
                t.setItem(r, c, QTableWidgetItem(v))
        design = _combo(list(DESIGN_LABELS.items()), s.get("design", "other"))
        basis = _combo(BASES, s.get("basis", "abstract"))
        design.currentIndexChanged.connect(lambda *_: self._sources_changed())
        basis.currentIndexChanged.connect(lambda *_: self._sources_changed())
        t.setCellWidget(r, 7, design)
        t.setCellWidget(r, 10, basis)
        t.blockSignals(False)

    def _add_empty_source(self) -> None:
        self._add_source({"key": "", "design": "other", "basis": "abstract"})
        self._sources_changed()

    def _add_claim(self, text: str = "", quote: str = "", source: str = "") -> None:
        t = self.claims_table
        t.blockSignals(True)
        r = t.rowCount()
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(text))
        t.setItem(r, 1, QTableWidgetItem(quote))
        box = QComboBox()
        box.setEditable(True)
        box.addItems(self._source_keys())
        box.setCurrentText(source or (self._source_keys() or [""])[0])
        box.currentTextChanged.connect(lambda *_: self._refresh_checks())
        t.setCellWidget(r, 2, box)
        status = QTableWidgetItem("")
        status.setFlags(status.flags() & ~Qt.ItemFlag.ItemIsEditable)
        t.setItem(r, 3, status)
        t.blockSignals(False)
        self._refresh_checks()

    def _add_position(self, label: str = "", summary: str = "", keys: str = "") -> None:
        t = self.positions_table
        r = t.rowCount()
        t.insertRow(r)
        for c, v in enumerate([label, summary, keys]):
            t.setItem(r, c, QTableWidgetItem(v))

    # --------------------------------------------------------- Zustaende ---

    def _cell(self, table: QTableWidget, r: int, c: int) -> str:
        item = table.item(r, c)
        return item.text().strip() if item else ""

    def _source_keys(self) -> list[str]:
        return [k for r in range(self.sources_table.rowCount()) if (k := self._cell(self.sources_table, r, 0))]

    def _source_row(self, key: str) -> int | None:
        return next((r for r in range(self.sources_table.rowCount()) if self._cell(self.sources_table, r, 0) == key), None)

    def _source_basis(self, key: str) -> str:
        r = self._source_row(key)
        return self.sources_table.cellWidget(r, 10).currentData() if r is not None else "abstract"

    def _is_paper_source(self, key: str) -> bool:
        r = self._source_row(key)
        return bool(self.paper and r is not None and self.paper.get("doi") and self._cell(self.sources_table, r, 5).lower() == self.paper["doi"])

    def _sources_changed(self) -> None:
        keys = self._source_keys()
        for r in range(self.claims_table.rowCount()):  # Auswahl der Quellen in den Aussagen aktuell halten
            box: QComboBox = self.claims_table.cellWidget(r, 2)
            current = box.currentText()
            box.blockSignals(True)
            box.clear()
            box.addItems(keys)
            box.setCurrentText(current)
            box.blockSignals(False)
        only_abstract = all(self._source_basis(k) != "fulltext" for k in keys) if keys else True
        self.cap_hint.setText("Alle Quellen nur über den Abstract geprüft: Das Backend erlaubt höchstens Evidenzstufe B."
                              if only_abstract else "Mindestens eine Quelle mit Volltext: Stufe A ist möglich, wenn sie ein Review, eine Metaanalyse oder ein "
                              "Konsens-Statement ist.")
        self._refresh_checks()

    def _status_changed(self) -> None:
        self.positions_box.setVisible(self.status.currentData() == "contested")

    def _refresh_checks(self) -> None:
        t = self.claims_table
        t.blockSignals(True)
        for r in range(t.rowCount()):
            quote, key = self._cell(t, r, 1), t.cellWidget(r, 2).currentText().strip() if t.cellWidget(r, 2) else ""
            words = len(quote.split())
            if words > 25:
                msg = f"✗ {words} Wörter (höchstens 25)"
            elif self.paper and self._is_paper_source(key):
                msg = "✓ steht im Abstract" if verify.quote_found(quote, self.paper.get("abstract", "")) else "✗ steht NICHT im Abstract"
            else:
                msg = "– nicht automatisch prüfbar"
            t.item(r, 3).setText(msg)
        t.blockSignals(False)

    # ----------------------------------------------------------- Speichern ---

    def _error(self, text: str) -> None:
        self.error.setText(text)

    def _collect(self) -> tuple[dict, list[dict], str]:
        sources = []
        for r in range(self.sources_table.rowCount()):
            def cell(c: int) -> str:
                return self._cell(self.sources_table, r, c)

            if not any(cell(c) for c in range(self.sources_table.columnCount()) if c not in (7, 10)):
                continue
            try:
                year = int(cell(2))
            except ValueError:
                raise ValueError(f"Quelle {cell(0) or r + 1}: Jahr muss eine Zahl sein")
            try:
                n = int(cell(8)) if cell(8) else None
            except ValueError:
                raise ValueError(f"Quelle {cell(0) or r + 1}: n muss eine ganze Zahl sein")
            flags = self._flags.get(cell(5).lower()) or self._flags.get(cell(0)) or {}
            sources.append({"key": cell(0), "authors": cell(1), "year": year, "title": cell(3), "journal": cell(4) or None,
                            "doi": cell(5) or None, "pmid": cell(6) or None, "design": self.sources_table.cellWidget(r, 7).currentData(),
                            "sample_n": n, "population": cell(9) or None, "basis": self.sources_table.cellWidget(r, 10).currentData(),
                            "retracted": flags.get("retracted", False), "retraction_checked": flags.get("retraction_checked")})
        claims = []
        for r in range(self.claims_table.rowCount()):
            text, quote = self._cell(self.claims_table, r, 0), self._cell(self.claims_table, r, 1)
            key = self.claims_table.cellWidget(r, 2).currentText().strip()
            if text or quote:
                claims.append({"text": text, "quote": quote, "source_key": key})
        positions = []
        for r in range(self.positions_table.rowCount()):
            label, summary, keys = (self._cell(self.positions_table, r, c) for c in range(3))
            if label or summary:
                positions.append({"label": label, "summary": summary, "source_keys": [k.strip() for k in keys.split(",") if k.strip()]})
        card = {
            "slug": self.slug.text().strip(), "title": self.title.text().strip(), "topic": self.topic.currentData(),
            "status": self.status.currentData(), "evidence": self.evidence.currentData(), "directness": self.directness.currentData(),
            "safety": self.safety.isChecked(), "tags": [t.strip() for t in self.tags.text().split(",") if t.strip()],
            "summary": self.summary.toPlainText().strip(), "recommendation": self.recommendation.toPlainText().strip(),
            "caveats": self.caveats.toPlainText().strip() or None,
            "applies_to": {"population": [k for k, b in self.pops.items() if b.isChecked()], "sex": self.sex.currentData(),
                           "age": self.age.text().strip() or None},
            "claims": claims, "positions": positions or None,
        }
        if self.existing and not self.review.isChecked():
            card["reviewed"], card["review_due"] = self._card.get("reviewed"), self._card.get("review_due")
        return card, sources, self.note.text().strip()

    def _save(self) -> None:
        self._error("")
        try:
            card, sources, note = self._collect()
        except ValueError as e:
            self._error(str(e))
            return
        if self.paper:  # Zitate gegen den Abstract pruefen, solange der Nutzer den Volltext nicht selbst bestaetigt hat
            for c in card["claims"]:
                if self._is_paper_source(c["source_key"]) and self._source_basis(c["source_key"]) == "abstract" \
                        and not verify.quote_found(c["quote"], self.paper.get("abstract", "")):
                    self._error(f"Das Zitat „{c['quote'][:70]}“ steht nicht im Abstract. Zitat korrigieren oder Basis auf „Volltext selbst gelesen“ "
                                "stellen, falls Du es dort gefunden hast.")
                    return
        try:
            self.submit(card, sources, note)
        except Exception as e:  # noqa: BLE001 - Backend-Meldung (z. B. Regelverstoss) im Dialog zeigen, Dialog offen lassen
            self._error(str(e))
            return
        self.accept()
