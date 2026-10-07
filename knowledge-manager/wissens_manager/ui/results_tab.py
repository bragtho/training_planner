"""Bereich 2: Ergebnisse mit KI-Zusammenfassung ansehen und entscheiden (aufnehmen, Watchlist, verwerfen)."""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QComboBox, QInputDialog, QLabel, QMessageBox, QPushButton, QSplitter, QVBoxLayout, QWidget

from .. import topics
from ..backend import BackendError
from .card_editor import CardEditorDialog
from .core import Services, Task
from .detail import ACTION_COLORS, candidate_widgets
from .render import ACTION_LABELS, candidate_title, evidence_cap, found_on, quote_summary
from .widgets import icon_button, GREEN, RED, CardList, DetailView, ListItem, Segmented, Toolbar, action_bar

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

        self.new_after_id: int | None = None  # Kandidaten mit hoeherer ID stammen aus der letzten Recherche
        self.status = Segmented([("Offen", "pending"), ("Watchlist", "watch"), ("Aufgenommen", "accepted"), ("Verworfen", "rejected")])
        self.scope = Segmented([("Alle", "all"), ("Neu", "new"), ("Älter", "old")])
        self.topic = QComboBox()
        self.topic.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.topic.setMinimumContentsLength(12)
        self.topic.addItem("Alle Themen", None)
        for key, (label, _) in topics.TOPICS.items():
            self.topic.addItem(label, key)
        self.refresh_btn = icon_button("refresh", "Aktualisieren")
        self.count = QLabel("")
        self.count.setObjectName("muted")
        top = Toolbar(self.status, self.scope, self.topic, self.refresh_btn, right=self.count)

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

        self.accept_btn = QPushButton("Aufnehmen …")
        self.accept_btn.setObjectName("primary")
        self.watch_btn = QPushButton("Auf die Watchlist")
        self.reject_btn = QPushButton("Verwerfen …")
        self.reject_btn.setObjectName("danger")
        self.open_btn = QPushButton("Studie im Browser öffnen")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(top)
        lay.addWidget(split, 1)
        lay.addWidget(action_bar(self.accept_btn, self.watch_btn, self.reject_btn, self.open_btn))

        self.status.currentIndexChanged.connect(self.refresh)
        self.topic.currentIndexChanged.connect(self._populate)
        self.scope.currentIndexChanged.connect(self._populate)
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
        self._task.failed.connect(lambda m: (self.count.setText(""), self.detail.show_message(m, "Fehler beim Laden")))
        self._task.start()

    def _loaded(self, items: list[dict]) -> None:
        self.items = sorted(items, key=lambda c: -c["id"])
        self._populate()

    def is_new(self, c: dict) -> bool:
        return self.new_after_id is not None and c["id"] > self.new_after_id

    def mark_new(self, after_id: int) -> None:
        """Ab jetzt gelten Kandidaten mit hoeherer ID als neu; die Ansicht springt auf die neuen."""
        self.new_after_id = after_id
        self.scope.blockSignals(True)
        self.scope.setCurrentIndex(self.scope.findData("new"))
        self.scope.blockSignals(False)

    def _populate(self) -> None:
        topic, scope = self.topic.currentData(), self.scope.currentData()
        shown = [c for c in self.items if (topic is None or c["topic"] == topic)
                 and (scope == "all" or (scope == "new") == self.is_new(c))]
        # Neue zuerst, innerhalb davon die neueste Studie zuerst
        shown.sort(key=lambda c: (not self.is_new(c), -c["id"]))
        self._shown = shown
        self.list.blockSignals(True)
        self.list.clear()
        for c in shown:
            self.list.add(candidate_title(c, new=self.is_new(c)), self._list_item(c))
        self.list.blockSignals(False)
        new_count = sum(1 for c in shown if self.is_new(c))
        self.count.setText(f"{len(shown)} Einträge" + (f" · {new_count} neu" if new_count and scope == "all" else ""))
        if shown:
            self.list.setCurrentRow(0)
            self._show(0)
        else:
            hint = {"new": "Keine neuen Studien aus der letzten Recherche.", "old": "Keine älteren Einträge."}.get(
                scope, "Keine Einträge. Starte eine Recherche oder wechsle den Status.")
            self.detail.show_message(hint)
            self._update_buttons()

    def current(self) -> dict | None:
        r = self.list.currentRow()
        shown = getattr(self, "_shown", [])
        return shown[r] if 0 <= r < len(shown) else None

    def _list_item(self, c: dict) -> ListItem:
        a = c.get("analysis") or {}
        ai, paper, chk = a.get("ai") or {}, a.get("paper") or {}, a.get("check") or {}
        new = self.is_new(c)
        meta = " · ".join(x for x in (topics.topic_label(c["topic"]), str(paper.get("year") or ""),
                                      "" if new else (f"gefunden {found_on(c)}" if found_on(c) else "")) if x)
        action = ai.get("suggested_action")
        pills = [("NEU", GREEN)] if new else []
        pills.append((ACTION_LABELS.get(action, "—"), ACTION_COLORS.get(action, "#64748b")))
        if (chk.get("retraction") or {}).get("status") == "retracted":
            pills.append(("zurückgezogen", RED))
        elif (chk.get("cross_check") or {}).get("verdict") == "issues" or quote_summary(chk)[0] is False:
            pills.append(("prüfen", RED))
        return ListItem(title=c["title"], meta=meta, pills=pills, highlight=new)

    def _show(self, _row: int) -> None:
        c = self.current()
        if c:
            self.detail.set_widgets(candidate_widgets(c, new=self.is_new(c)))
        else:
            self.detail.clear()
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
