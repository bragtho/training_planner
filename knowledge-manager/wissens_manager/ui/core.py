"""Gemeinsame Qt-Bausteine: Dienste (Backend, KI), Hintergrund-Aufgaben und Stil."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx
from PyQt6.QtCore import QThread, pyqtSignal

from ..ai import AiAdapter, ClaudeCliAdapter
from ..backend import BackendClient
from ..config import Config


@dataclass
class Services:
    cfg: Config
    backend: BackendClient
    ai: AiAdapter
    epmc_http: httpx.Client | None = None
    crossref_http: httpx.Client | None = None

    @classmethod
    def from_config(cls, cfg: Config) -> "Services":
        return cls(cfg, BackendClient(cfg.backend_url, cfg.admin_token), ClaudeCliAdapter(cfg.claude_path, cfg.model, cfg.ai_timeout))


class Task(QThread):
    """Fuehrt eine Funktion im Hintergrund aus, damit die Oberflaeche nie blockiert.

    fn(progress, cancelled) -> Ergebnis; progress(stage, done, total, message) meldet Fortschritt,
    cancelled() wird True, wenn der Nutzer abbricht (requestInterruption).
    """

    progress = pyqtSignal(str, int, int, str)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[Callable[..., None], Callable[[], bool]], Any], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn(self.progress.emit, self.isInterruptionRequested)
        except Exception as e:  # noqa: BLE001 - jede Fehlerart soll als Meldung beim Nutzer landen
            self.failed.emit(str(e) or e.__class__.__name__)
            return
        self.done.emit(result)


# Farben und Radien wie in der App (app/lib/core/theme.dart), damit beide gleich aussehen.
PALETTE = {
    False: dict(bg="#f4f6f8", card="#ffffff", container="#eef1f4", high="#e7ebef", line="#e2e7ec", text="#141a21", muted="#5b6776",
                accent="#0b7a55", on_accent="#ffffff", brand="#0fa968"),
    True: dict(bg="#0e1116", card="#151a21", container="#1a2029", high="#212833", line="#2a323d", text="#e6eaf0", muted="#8b97a7",
               accent="#34d399", on_accent="#052e1f", brand="#0fa968"),
}
FONT = 'Roboto, "Segoe UI", sans-serif'
CURRENT_DARK = True  # zuletzt gesetztes Farbschema (fuer selbst gezeichnete Elemente)
ICONS = {"refresh": 0xE514, "add": 0xE047, "search": 0xE567, "fact_check": 0xE256, "library": 0xE377, "settings": 0xE57F, "bike": 0xF6AD, "check": 0xE156}


def is_dark(theme: str, app=None) -> bool:
    if theme == "system" and app is not None:
        from PyQt6.QtGui import QPalette

        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return theme != "light" and theme != "system"


def material_icon(name: str, color: str, size: int = 22):
    """Zeichnet ein Material-Symbol (gleiche Schrift wie in der App) als QIcon."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Material Icons")
    font.setPixelSize(size * scale)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(0, 0, size * scale, size * scale), Qt.AlignmentFlag.AlignCenter, chr(ICONS[name]))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def stylesheet(dark: bool) -> str:
    c = PALETTE[dark]
    tint = "rgba(52,211,153,0.14)" if dark else "rgba(11,122,85,0.12)"
    return f"""
* {{ font-family: {FONT}; font-size: 14px; }}
QWidget {{ background: {c['bg']}; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['bg']}; }}
QMenu {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {tint}; color: {c['accent']}; }}
QFrame#sidebar {{ background: {c['card']}; border: none; border-right: 1px solid {c['line']}; }}
QFrame#sidebar QLabel {{ background: transparent; }}
QFrame#sidebar QPushButton {{ background: transparent; }}
QFrame#sidebar QLabel#logo {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c['brand']}, stop:1 #3b82f6); border-radius: 12px; }}
QFrame#sidebar QLabel#brand {{ font-size: 16px; font-weight: 800; }}
QFrame#sidebar QLabel#brand2 {{ font-size: 16px; font-weight: 800; color: {c['accent']}; }}
QPushButton#nav {{ border: none; border-radius: 16px; padding: 12px 16px; text-align: left; color: {c['muted']}; font-weight: 500; }}
QPushButton#nav:hover {{ background: {c['container']}; }}
QPushButton#nav:checked {{ background: {tint}; color: {c['accent']}; font-weight: 700; }}
QLabel#overline {{ padding-left: 0px; color: {c['accent']}; font-size: 12px; font-weight: 700; letter-spacing: 1.1px; }}
QLabel#pagetitle {{ padding-left: 0px; font-size: 28px; font-weight: 700; letter-spacing: -0.6px; }}
QLabel#status {{ color: {c['muted']}; font-size: 12px; }}
QTabWidget::pane {{ border: none; background: {c['bg']}; top: 0px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
  background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; padding: 10px 14px;
  selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 2px solid {c['accent']}; padding: 9px 13px; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 8px; outline: none;
  selection-background-color: {tint}; selection-color: {c['accent']}; }}
QTextBrowser, QListWidget, QTableWidget, QTreeWidget {{
  background: {c['card']}; border: 1px solid {c['line']}; border-radius: 20px; padding: 10px; outline: none; }}
QListWidget::item {{ padding: 10px 12px; border-radius: 12px; margin: 2px 0; }}
QListWidget::item:hover {{ background: {c['container']}; }}
QListWidget::item:selected {{ background: {tint}; color: {c['accent']}; }}
QPushButton {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 12px; padding: 12px 20px; font-weight: 600; }}
QPushButton:hover {{ background: {c['container']}; }}
QPushButton:pressed {{ background: {c['high']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['container']}; }}
QPushButton#primary {{ background: {c['accent']}; color: {c['on_accent']}; border: none; }}
QPushButton#icon {{ padding: 0; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; }}
QPushButton#primary:hover {{ background: {c['brand']}; }}
QPushButton#primary:disabled {{ background: {c['high']}; color: {c['muted']}; }}
QPushButton#danger {{ color: #ef4444; }}
QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1.5px solid {c['muted']}; border-radius: 5px; background: {c['card']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QGroupBox {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 20px; margin-top: 0; padding: 48px 16px 16px 16px; font-weight: 700; }}
QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left; left: 20px; top: 16px; color: {c['text']}; background: transparent; font-size: 16px; }}
QProgressBar {{ border: none; border-radius: 8px; background: {c['high']}; text-align: center; min-height: 16px; max-height: 16px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 8px; }}
QHeaderView::section {{ background: {c['card']}; border: none; border-bottom: 1px solid {c['line']}; padding: 8px; font-weight: 700; color: {c['muted']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {c['high']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {c['high']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle {{ background: transparent; width: 16px; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {c['muted']}; }}
QLabel#error {{ color: #ef4444; font-weight: 600; }}
QLabel#h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.4px; }}
QLabel#h2 {{ font-size: 18px; font-weight: 700; }}
QLabel#h3 {{ font-size: 15px; font-weight: 700; }}
QLabel#body {{ font-size: 14px; }}
QLabel#small {{ font-size: 12px; color: {c['muted']}; }}
QLabel#caption {{ font-size: 12px; font-weight: 600; color: {c['muted']}; }}
QLabel#overline2 {{ color: {c['accent']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QFrame#card {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 20px; }}
QFrame#card QLabel, QFrame#card QCheckBox {{ background: transparent; }}
QFrame#card QTableWidget {{ background: {c['bg']}; border: 1px solid {c['line']}; border-radius: 12px; padding: 4px; gridline-color: {c['line']}; }}
QTableWidget::item {{ padding: 6px; }}
QTableWidget QComboBox, QTableWidget QLineEdit {{ padding: 2px 8px; border-radius: 6px; min-height: 0; margin: 4px; }}
QTableWidget::item:selected {{ background: {tint}; color: {c['text']}; }}
QWidget#plain {{ background: transparent; }}
QWidget#segmented {{ background: {c['container']}; border: 1px solid {c['line']}; border-radius: 12px; }}
QPushButton#seg {{ background: transparent; border: none; border-radius: 9px; padding: 7px 12px; color: {c['muted']}; font-weight: 600; }}
QPushButton#seg:hover {{ color: {c['text']}; }}
QPushButton#seg:checked {{ background: {c['card']}; color: {c['accent']}; font-weight: 700; }}
QScrollArea#detail, QWidget#detailInner {{ background: transparent; border: none; }}
QListWidget#cards {{ background: transparent; border: none; padding: 0; }}
QListWidget#cards::item, QListWidget#cards::item:hover, QListWidget#cards::item:selected {{ background: transparent; padding: 0; margin: 0; }}
QPlainTextEdit#log {{ background: {c['card']}; border: 1px solid {c['line']}; border-radius: 16px; padding: 12px 14px;
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 12px; color: {c['muted']}; }}
QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['line']}; border-radius: 8px; padding: 6px; }}
"""


def apply_theme(app, dark: bool) -> None:
    """Schriften laden, Stylesheet und Linkfarbe (Palette) wie in der App setzen."""
    from pathlib import Path

    global CURRENT_DARK
    CURRENT_DARK = dark

    from PyQt6.QtGui import QColor, QFontDatabase, QPalette

    for font_file in sorted((Path(__file__).resolve().parent.parent / "fonts").glob("*")):
        if font_file.suffix.lower() in (".ttf", ".otf"):
            QFontDatabase.addApplicationFont(str(font_file))
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.Link, QColor(PALETTE[dark]["accent"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(dark))
