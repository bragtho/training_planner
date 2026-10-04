"""Hauptfenster: drei Bereiche (Recherche, Ergebnisse, Wissensbasis), Einstellungen und Statusanzeige."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                             QMessageBox, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..ai import ClaudeCliAdapter
from ..backend import BackendError
from ..config import Config, save_config
from .core import PALETTE, Services, Task, apply_theme, is_dark, material_icon
from .knowledge_tab import KnowledgeTab
from .research_tab import ResearchTab
from .results_tab import ResultsTab


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg: Config):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.resize(560, 420)
        self.cfg = cfg
        self.url = QLineEdit(cfg.backend_url)
        self.token = QLineEdit(cfg.admin_token)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("KNOWLEDGE_ADMIN_TOKEN aus backend/.env")
        self.claude = QLineEdit(cfg.claude_path)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["sonnet", "opus", "haiku"])
        self.model.setCurrentText(cfg.model)
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 3)
        self.parallel.setValue(cfg.parallel)
        self.batch = QSpinBox()
        self.batch.setRange(1, 8)
        self.batch.setValue(cfg.batch_size)
        self.theme = QComboBox()
        for key, label in (("dark", "Dunkel"), ("light", "Hell"), ("system", "Wie Windows")):
            self.theme.addItem(label, key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(cfg.theme)))
        self.max = QSpinBox()
        self.max.setRange(1, 100)
        self.max.setValue(cfg.max_papers)
        form = QFormLayout()
        form.addRow("Backend-Adresse", self.url)
        form.addRow("Verwaltungsschlüssel", self.token)
        form.addRow("Claude-Programm", self.claude)
        form.addRow("Modell", self.model)
        form.addRow("Gleichzeitige KI-Aufrufe", self.parallel)
        form.addRow("Abstracts je KI-Aufruf", self.batch)
        form.addRow("Neue Studien je Recherche", self.max)
        form.addRow("Farbschema", self.theme)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        test = QPushButton("Verbindungen testen")
        test.clicked.connect(self._test)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(test)
        lay.addWidget(self.result)
        lay.addStretch()
        lay.addWidget(buttons)

    def values(self) -> Config:
        return Config(backend_url=self.url.text(), admin_token=self.token.text().strip(), claude_path=self.claude.text().strip() or "claude",
                      model=self.model.currentText().strip() or "sonnet", parallel=self.parallel.value(), batch_size=self.batch.value(),
                      max_papers=self.max.value(), ai_timeout=self.cfg.ai_timeout, theme=self.theme.currentData()).clamp()

    def _test(self) -> None:
        s = Services.from_config(self.values())
        lines = []
        try:
            info = s.backend.ping()
            lines.append(f"✓ Backend erreichbar, Schlüssel passt ({info['dois']} bekannte Studien)")
        except BackendError as e:
            lines.append(f"✗ Backend: {e}")
        version = s.ai.available() if isinstance(s.ai, ClaudeCliAdapter) else None
        lines.append(f"✓ Claude-Programm: {version}" if version else "✗ Claude-Programm nicht startbar (Pfad prüfen, einmal `claude` im Terminal anmelden)")
        self.result.setText("\n".join(lines))


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config, services: Services | None = None, *, check_connections: bool = True):
        super().__init__()
        self.cfg = cfg
        self._dark = is_dark(cfg.theme, QApplication.instance())
        self._services = services or Services.from_config(cfg)
        self.setWindowTitle(f"Wissens-Manager {__version__}")
        self.resize(1180, 820)

        self.research = ResearchTab(self.get_services)
        self.results = ResultsTab(self.get_services)
        self.knowledge = KnowledgeTab(self.get_services)
        tabs = QTabWidget()
        tabs.addTab(self.research, "Recherche")
        tabs.addTab(self.results, "Ergebnisse")
        tabs.addTab(self.knowledge, "Wissensbasis")
        tabs.tabBar().hide()
        self.tabs = tabs

        self.backend_label = QLabel("Backend: …")
        self.ai_label = QLabel("KI: …")
        for label in (self.backend_label, self.ai_label):
            label.setObjectName("status")
            label.setWordWrap(True)

        self.page_overline = QLabel()
        self.page_overline.setObjectName("overline")
        self.page_title = QLabel()
        self.page_title.setObjectName("pagetitle")
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(40, 24, 32, 24)
        col.setSpacing(0)
        col.addWidget(self.page_overline)
        col.addWidget(self.page_title)
        col.addSpacing(20)
        col.addWidget(tabs, 1)

        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._sidebar())
        row.addWidget(content, 1)
        self.setCentralWidget(central)
        self._show_page(0)

        self.research.finished.connect(lambda: (self.results.refresh(), tabs.setCurrentWidget(self.results)))
        self.results.changed.connect(self.knowledge.refresh)
        tabs.currentChanged.connect(self._tab_changed)
        tabs.currentChanged.connect(self._show_page)
        self._checks: list[Task] = []
        if check_connections:
            self.check_connections()
            self.results.refresh()

    PAGES = (("Schritt 1 von 3", "Recherche", "search"), ("Schritt 2 von 3", "Ergebnisse", "fact_check"),
             ("Schritt 3 von 3", "Wissensbasis", "library"))

    def _sidebar(self) -> QFrame:
        """Seitenleiste wie in der App: Logo, Navigation mit Symbolen, unten Status und Einstellungen."""
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(240)
        col = QVBoxLayout(frame)
        col.setContentsMargins(16, 20, 16, 16)
        col.setSpacing(4)

        logo = QLabel()
        logo.setObjectName("logo")
        logo.setFixedSize(40, 40)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(material_icon("bike", "#ffffff", 24).pixmap(24, 24))
        brand, brand2 = QLabel("Wissens-"), QLabel("Manager")
        brand.setObjectName("brand")
        brand2.setObjectName("brand2")
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(brand)
        names.addWidget(brand2)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(logo)
        head.addLayout(names)
        head.addStretch()
        col.addLayout(head)
        col.addSpacing(20)

        self.nav: list[QPushButton] = []
        for i, (_, title, icon) in enumerate(self.PAGES):
            btn = QPushButton(f"  {title}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIconSize(QSize(22, 22))
            btn.clicked.connect(lambda _=False, n=i: self.tabs.setCurrentIndex(n))
            col.addWidget(btn)
            self.nav.append(btn)
        col.addStretch()

        settings = QPushButton("  Einstellungen")
        settings.setObjectName("nav")
        settings.setCursor(Qt.CursorShape.PointingHandCursor)
        settings.setIconSize(QSize(22, 22))
        settings.clicked.connect(self.open_settings)
        self.settings_btn = settings
        col.addWidget(self.backend_label)
        col.addWidget(self.ai_label)
        col.addSpacing(8)
        col.addWidget(settings)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("status")
        col.addWidget(version)
        self._paint_icons()
        return frame

    def _paint_icons(self) -> None:
        dark = self._dark
        c = PALETTE[dark]
        for i, btn in enumerate(self.nav):
            btn.setIcon(material_icon(self.PAGES[i][2], c["accent"] if btn.isChecked() else c["muted"]))
        self.settings_btn.setIcon(material_icon("settings", c["muted"]))

    def _show_page(self, index: int) -> None:
        overline, title, _ = self.PAGES[index]
        self.page_overline.setText(overline.upper())
        self.page_title.setText(title)
        for i, btn in enumerate(self.nav):
            btn.setChecked(i == index)
        self._paint_icons()

    def get_services(self) -> Services:
        return self._services

    def _tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.knowledge and not self.knowledge.cards:
            self.knowledge.refresh()

    def check_connections(self) -> None:
        s = self._services
        backend = Task(lambda progress, cancelled: s.backend.ping(), self)
        backend.done.connect(lambda info: self.backend_label.setText(f"Backend verbunden · {info['dois']} bekannte Studien"))
        backend.failed.connect(lambda m: self.backend_label.setText(f"Backend: {m[:110]}"))
        ai = Task(lambda progress, cancelled: s.ai.available() if isinstance(s.ai, ClaudeCliAdapter) else "bereit", self)
        ai.done.connect(lambda v: self.ai_label.setText(f"KI: Claude {v} (Abo)" if v else "KI: Claude-Programm nicht gefunden"))
        ai.failed.connect(lambda m: self.ai_label.setText(f"KI: {m[:80]}"))
        self._checks = [backend, ai]
        for t in self._checks:
            t.start()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec():
            self.cfg = dlg.values()
            try:
                save_config(self.cfg)
            except OSError as e:
                QMessageBox.warning(self, "Einstellungen", f"Konnte nicht gespeichert werden: {e}")
            self._services = Services.from_config(self.cfg)
            self._dark = is_dark(self.cfg.theme, QApplication.instance())
            apply_theme(QApplication.instance(), self._dark)
            self._paint_icons()
            self.check_connections()
            self.results.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt-Name
        for tab in (self.research,):
            task = getattr(tab, "_task", None)
            if task is not None and task.isRunning():
                task.requestInterruption()
                task.wait(3000)
        super().closeEvent(event)
