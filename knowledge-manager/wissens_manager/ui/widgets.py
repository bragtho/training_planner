"""Bausteine im Stil der App: Karten, Pillen, Segment-Schalter, Listeneintraege als Karten und eine Detailansicht aus Widgets.

Die Listen zeichnen ihre Eintraege selbst (ListCardDelegate): Titel bis drei Zeilen mit sauberem Auslassungszeichen,
Metazeile und Pillen, die bei Bedarf umbrechen. So wird nichts abgeschnitten, und Abstaende sind ueberall gleich.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QModelIndex, QPoint, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PyQt6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem, QPushButton,
                             QScrollArea, QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget)

from . import core

# Farben mit fester Bedeutung, wie in der App (AppColors / evidenceColor)
GREEN, BLUE, AMBER, RED, SLATE, VIOLET, ORANGE = "#16a34a", "#3b82f6", "#f59e0b", "#ef4444", "#64748b", "#a855f7", "#f97316"
EVIDENCE_COLORS = {"A": GREEN, "B": BLUE, "C": AMBER, "D": SLATE}

ITEM_ROLE = Qt.ItemDataRole.UserRole + 1  # ListItem fuer den Delegate


def palette() -> dict:
    return core.PALETTE[core.CURRENT_DARK]


def rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


# --------------------------------------------------------------- Layouts ---


class FlowLayout(QLayout):
    """Ordnet Elemente nebeneinander an und bricht in die naechste Zeile um (fuer Pillen)."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt-Name
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, i: int) -> QLayoutItem | None:  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i: int) -> QLayoutItem | None:  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), dry=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, dry=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _layout(self, rect: QRect, dry: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            if x + hint.width() > rect.right() + 1 and line > 0:
                x, y, line = rect.x(), y + line + self._spacing, 0
            if not dry:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line = max(line, hint.height())
        return y + line - rect.y()


# --------------------------------------------------------------- Bausteine ---


def label(text: str = "", kind: str = "body", *, wrap: bool = True, selectable: bool = False) -> QLabel:
    """Text mit Rolle (h1, h2, h3, body, muted, small, overline). Rich Text nur, wo ausdruecklich gewollt."""
    lab = QLabel(text)
    lab.setObjectName(kind)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.TextFormat.PlainText)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lab


def link_label(text: str, url: str) -> QLabel:
    lab = QLabel(f'<a href="{url}" style="color:{palette()["accent"]}; text-decoration:none">{text}</a>')
    lab.setObjectName("small")
    lab.setTextFormat(Qt.TextFormat.RichText)
    lab.setOpenExternalLinks(True)
    return lab


class Pill(QLabel):
    """Farbige Kennzeichnung wie in der App (Pill): getoenter Hintergrund, kraeftige Schrift."""

    def __init__(self, text: str, color: str, *, filled: bool = False):
        super().__init__(text)
        self.setObjectName("pill")
        fg = "#ffffff" if filled else color
        bg = color if filled else rgba(color, 0.15)
        self.setStyleSheet(f"QLabel#pill {{ background: {bg}; color: {fg}; border-radius: 11px; padding: 3px 10px;"
                           f" font-size: 12px; font-weight: 700; }}")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)


def pill_row(pills: list[tuple[str, str]]) -> QWidget:
    w = QWidget()
    w.setObjectName("plain")
    flow = FlowLayout(w, spacing=8)
    for text, color in pills:
        flow.addWidget(Pill(text, color))
    return w


class Card(QFrame):
    """Karte mit feinem Rahmen (SurfaceCard der App), optional mit Titel und Untertitel."""

    def __init__(self, title: str | None = None, subtitle: str | None = None, *, tone: str | None = None, spacing: int = 10):
        super().__init__()
        self.setObjectName("card")
        if tone:  # getoente Karte, z. B. fuer Warnungen
            self.setStyleSheet(f"QFrame#card {{ background: {rgba(tone, 0.08)}; border: 1px solid {rgba(tone, 0.35)}; }}")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(20, 18, 20, 18)
        self.body.setSpacing(spacing)
        if title:
            self.body.addWidget(label(title, "h3"))
        if subtitle:
            self.body.addWidget(label(subtitle, "muted"))
            self.body.addSpacing(2)

    def add(self, widget: QWidget) -> QWidget:
        self.body.addWidget(widget)
        return widget


def status_row(state: bool | None, text: str) -> QWidget:
    """Pruefzeile mit Symbol (gruen, rot, grau) und Text."""
    color, mark = (GREEN, "✓") if state is True else (RED, "✕") if state is False else (SLATE, "–")
    w = QWidget()
    w.setObjectName("plain")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(10)
    icon = QLabel(mark)
    icon.setFixedSize(22, 22)
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setStyleSheet(f"background: {rgba(color, 0.16)}; color: {color}; border-radius: 11px; font-weight: 800;")
    row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    row.addWidget(label(text), 1)
    return w


def bullet_list(items: list[str], color: str | None = None, *, quote: bool = False) -> QWidget:
    w = QWidget()
    w.setObjectName("plain")
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(8)
    for text in items:
        row = QHBoxLayout()
        row.setSpacing(10)
        dot = QLabel("•")
        dot.setStyleSheet(f"color: {color or palette()['muted']}; font-weight: 800;")
        row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        lab = label(f"„{text}“" if quote else text, "body", selectable=True)
        if quote:
            lab.setStyleSheet("font-style: italic;")
        row.addWidget(lab, 1)
        col.addLayout(row)
    return w


class Segmented(QWidget):
    """Segment-Schalter wie SegmentedButton der App. Bietet die wichtigsten QComboBox-Methoden, damit er sie ersetzen kann."""

    currentIndexChanged = pyqtSignal(int)  # noqa: N815 - Qt-Name

    def __init__(self, options: list[tuple[str, object]]):
        super().__init__()
        self.setObjectName("segmented")
        self._data = [d for _, d in options]
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        for i, (text, _) in enumerate(options):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(b, i)
            row.addWidget(b)
        self._group.buttons()[0].setChecked(True)
        self._group.idToggled.connect(lambda i, on: on and self.currentIndexChanged.emit(i))

    def count(self) -> int:
        return len(self._data)

    def currentIndex(self) -> int:  # noqa: N802
        return self._group.checkedId()

    def currentData(self):  # noqa: N802
        return self._data[self.currentIndex()]

    def findData(self, value) -> int:  # noqa: N802
        return self._data.index(value) if value in self._data else -1

    def setCurrentIndex(self, i: int) -> None:  # noqa: N802
        if 0 <= i < len(self._data) and i != self.currentIndex():
            self._group.button(i).setChecked(True)

    def button(self, i: int) -> QAbstractButton:
        return self._group.button(i)


class DetailView(QScrollArea):
    """Rechte Spalte: Inhalt aus Karten, scrollbar. toPlainText() liefert den sichtbaren Text (fuer Tests und Kopieren)."""

    def __init__(self):
        super().__init__()
        self.setObjectName("detail")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._inner.setObjectName("detailInner")
        self._col = QVBoxLayout(self._inner)
        self._col.setContentsMargins(0, 0, 8, 0)
        self._col.setSpacing(16)
        self.setWidget(self._inner)

    def clear(self) -> None:
        while self._col.count():
            it = self._col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def set_widgets(self, widgets: list[QWidget]) -> None:
        self.clear()
        for w in widgets:
            self._col.addWidget(w)
        self._col.addStretch(1)
        self.verticalScrollBar().setValue(0)

    def show_message(self, text: str, title: str | None = None) -> None:
        card = Card(title)
        card.add(label(text, "muted"))
        self.set_widgets([card])

    def toPlainText(self) -> str:  # noqa: N802
        return "\n".join(lab.text() for lab in self._inner.findChildren(QLabel) if lab.text())

    toHtml = toPlainText  # noqa: N815 - frueherer QTextBrowser-Name


# ------------------------------------------------------------- Listenkarten ---


@dataclass
class ListItem:
    title: str
    meta: str = ""
    pills: list[tuple[str, str]] = field(default_factory=list)
    highlight: bool = False  # z. B. neu aus der letzten Recherche (Akzentstreifen links)
    badge: tuple[str, str] | None = None  # (Text, Farbe) kleines Kaestchen links, z. B. Evidenzstufe


class ListCardDelegate(QStyledItemDelegate):
    """Zeichnet Listeneintraege als Karten: Titel (bis 3 Zeilen), Metazeile, Pillen. Hoehe passt sich dem Inhalt an."""

    PAD_X, PAD_Y, GAP, RADIUS, MAX_TITLE_LINES = 16, 14, 6, 14, 3
    SPACING = 14  # Abstand zwischen zwei Karten

    def _fonts(self, base: QFont) -> tuple[QFont, QFont, QFont]:
        title = QFont(base)
        title.setPixelSize(14)
        title.setWeight(QFont.Weight.DemiBold)
        meta = QFont(base)
        meta.setPixelSize(12)
        pill = QFont(base)
        pill.setPixelSize(11)
        pill.setWeight(QFont.Weight.Bold)
        return title, meta, pill

    @staticmethod
    def _lines(text: str, font: QFont, width: int, max_lines: int) -> list[str]:
        """Bricht Text an Wortgrenzen um (sehr lange Woerter zeichenweise); die letzte erlaubte Zeile bekommt bei Bedarf ein
        Auslassungszeichen. Bewusst ohne QTextLayout: das stuerzte beim Neu-Stylen geloeschter Listen ab."""
        fm = QFontMetrics(font)
        lines: list[str] = []
        cur = ""
        for word in text.split():
            cand = f"{cur} {word}" if cur else word
            if fm.horizontalAdvance(cand) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = word
            while fm.horizontalAdvance(cur) > width and len(cur) > 1:  # ueberlanges Wort zerteilen
                k = len(cur)
                while k > 1 and fm.horizontalAdvance(cur[:k]) > width:
                    k -= 1
                lines.append(cur[:k])
                cur = cur[k:]
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            rest = " ".join(lines[max_lines - 1:])
            lines = lines[: max_lines - 1] + [fm.elidedText(rest, Qt.TextElideMode.ElideRight, width)]
        return lines or [""]

    def _pill_rows(self, pills: list[tuple[str, str]], font: QFont, width: int) -> list[list[tuple[str, str, int]]]:
        fm = QFontMetrics(font)
        rows: list[list[tuple[str, str, int]]] = [[]]
        x = 0
        for text, color in pills:
            w = fm.horizontalAdvance(text) + 16
            if rows[-1] and x + w > width:
                rows.append([])
                x = 0
            rows[-1].append((text, color, w))
            x += w + 6
        return [r for r in rows if r]

    def _content_width(self, width: int, item: ListItem) -> int:
        w = width - 2 * self.PAD_X - 8
        if item.badge:
            w -= 40
        return max(80, w)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        item: ListItem = index.data(ITEM_ROLE)
        if item is None:
            return super().sizeHint(option, index)
        # Breite aus der eigenen Liste (option.widget kann beim Neu-Stylen auf ein geloeschtes Objekt zeigen)
        view = self.parent()
        width = view.viewport().width() if view is not None else 360
        title_f, meta_f, pill_f = self._fonts(option.font)
        cw = self._content_width(width, item)
        h = self.PAD_Y * 2 + len(self._lines(item.title, title_f, cw, self.MAX_TITLE_LINES)) * QFontMetrics(title_f).lineSpacing()
        if item.meta:
            h += self.GAP + len(self._lines(item.meta, meta_f, cw, 2)) * QFontMetrics(meta_f).lineSpacing()
        rows = self._pill_rows(item.pills, pill_f, cw)
        if rows:
            h += self.GAP + 4 + len(rows) * (QFontMetrics(pill_f).height() + 8) + (len(rows) - 1) * 6
        return QSize(width, h + self.SPACING)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        item: ListItem = index.data(ITEM_ROLE)
        if item is None:
            return super().paint(painter, option, index)
        c = palette()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect.adjusted(1, 1, -2, -self.SPACING))
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        bg = QColor(c["accent"]) if selected else QColor(c["container"] if hover else c["card"])
        if selected:
            bg.setAlphaF(0.14)
        painter.fillPath(path, bg)
        painter.setPen(QColor(c["accent"]) if selected else QColor(c["line"]))
        painter.drawPath(path)
        if item.highlight:  # Akzentstreifen links
            painter.fillRect(QRectF(rect.left() + 1, rect.top() + 12, 4, rect.height() - 24), QColor(c["accent"]))

        title_f, meta_f, pill_f = self._fonts(option.font)
        x = int(rect.left()) + self.PAD_X + (4 if item.highlight else 0)
        y = int(rect.top()) + self.PAD_Y
        if item.badge:
            text, color = item.badge
            box = QRectF(x, y, 30, 30)
            bp = QPainterPath()
            bp.addRoundedRect(box, 8, 8)
            painter.fillPath(bp, QColor(color))
            painter.setPen(QColor("#ffffff"))
            bf = QFont(title_f)
            bf.setWeight(QFont.Weight.ExtraBold)
            painter.setFont(bf)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
            x += 40
        cw = self._content_width(option.rect.width(), item)

        painter.setFont(title_f)
        painter.setPen(QColor(c["accent"] if selected else c["text"]))
        fm = QFontMetrics(title_f)
        for line in self._lines(item.title, title_f, cw, self.MAX_TITLE_LINES):
            painter.drawText(QRect(x, y, cw, fm.lineSpacing()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
            y += fm.lineSpacing()
        if item.meta:
            y += self.GAP
            painter.setFont(meta_f)
            painter.setPen(QColor(c["muted"]))
            mfm = QFontMetrics(meta_f)
            for line in self._lines(item.meta, meta_f, cw, 2):
                painter.drawText(QRect(x, y, cw, mfm.lineSpacing()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
                y += mfm.lineSpacing()
        rows = self._pill_rows(item.pills, pill_f, cw)
        if rows:
            y += self.GAP + 4
            painter.setFont(pill_f)
            ph = QFontMetrics(pill_f).height() + 8
            for row in rows:
                px = x
                for text, color, w in row:
                    pr = QRectF(px, y, w, ph)
                    pp = QPainterPath()
                    pp.addRoundedRect(pr, ph / 2, ph / 2)
                    tint = QColor(color)
                    tint.setAlphaF(0.16)
                    painter.fillPath(pp, tint)
                    painter.setPen(QColor(color))
                    painter.drawText(pr, Qt.AlignmentFlag.AlignCenter, text)
                    px += w + 6
                y += ph + 6
        painter.restore()


class CardList(QWidget):
    """Liste aus Karten (ListCardDelegate). Bietet die Methoden von QListWidget, die die Bereiche nutzen."""

    currentRowChanged = pyqtSignal(int)  # noqa: N815 - Qt-Name

    def __init__(self):
        super().__init__()
        from PyQt6.QtWidgets import QAbstractItemView, QListWidget

        self.view = QListWidget()
        self.view.setObjectName("cards")
        self._delegate = ListCardDelegate(self.view)  # Referenz halten, sonst raeumt Python den Delegate weg
        self.view.setItemDelegate(self._delegate)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setUniformItemSizes(False)
        self.view.setMouseTracking(True)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.currentRowChanged.connect(self.currentRowChanged.emit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.view.setViewportMargins(0, 0, 6, 0)  # Luft zwischen Karten und Scrollbalken

    def resizeEvent(self, e) -> None:  # noqa: N802 - Hoehen haengen von der Breite ab
        super().resizeEvent(e)
        self.view.doItemsLayout()

    def add(self, text: str, item: ListItem) -> None:
        from PyQt6.QtWidgets import QListWidgetItem

        it = QListWidgetItem(text)  # Text fuer Barrierefreiheit und Tests; gezeichnet wird ListItem
        it.setData(ITEM_ROLE, item)
        it.setToolTip(item.title)
        self.view.addItem(it)

    def clear(self) -> None:
        self.view.clear()

    def count(self) -> int:
        return self.view.count()

    def item(self, i: int):
        return self.view.item(i)

    def currentRow(self) -> int:  # noqa: N802
        return self.view.currentRow()

    def setCurrentRow(self, i: int) -> None:  # noqa: N802
        self.view.setCurrentRow(i)

    def blockSignals(self, b: bool) -> bool:  # noqa: N802
        self.view.blockSignals(b)
        return super().blockSignals(b)


class Toolbar(QWidget):
    """Filterleiste: Elemente mit gleichmaessigem Abstand, rechts ein Zaehler."""

    def __init__(self, *widgets: QWidget, right: QWidget | None = None):
        super().__init__()
        self.setObjectName("plain")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        for w in widgets:
            row.addWidget(w)
        row.addStretch(1)
        if right is not None:
            row.addWidget(right)


def labeled(caption: str, widget: QWidget) -> QWidget:
    """Feld mit kleiner Beschriftung darueber (wie die Formularfelder der App)."""
    w = QWidget()
    w.setObjectName("plain")
    col = QVBoxLayout(w)
    col.setContentsMargins(0, 0, 0, 0)
    col.setSpacing(6)
    col.addWidget(label(caption, "caption", wrap=False))
    col.addWidget(widget)
    return w


def action_bar(*buttons: QWidget) -> QWidget:
    w = QWidget()
    w.setObjectName("plain")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 4, 0, 0)
    row.setSpacing(10)
    for b in buttons:
        row.addWidget(b)
    row.addStretch(1)
    return w


def plain(widget: QWidget) -> QWidget:
    """Container ohne eigenen Hintergrund (liegt auf Karten)."""
    widget.setObjectName("plain")
    return widget


class DialogFrame:
    """Geruest fuer Dialoge: Kopf (Titel, Untertitel), scrollbarer Inhalt aus Karten, Fusszeile mit Knoepfen."""

    def __init__(self, dlg: QWidget, title: str, subtitle: str | None = None, *, scroll: bool = True):
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(16)
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label(title, "h2"))
        if subtitle:
            head.addWidget(label(subtitle, "muted"))
        outer.addLayout(head)
        inner = QWidget()
        inner.setObjectName("detailInner")
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(0, 0, 8 if scroll else 0, 0)
        self.content.setSpacing(16)
        if scroll:
            area = QScrollArea()
            area.setObjectName("detail")
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            area.setWidget(inner)
            outer.addWidget(area, 1)
        else:
            outer.addWidget(inner, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(10)
        outer.addLayout(self.footer)

    def add(self, widget: QWidget) -> QWidget:
        self.content.addWidget(widget)
        return widget


def icon_button(icon: str, tooltip: str) -> QPushButton:
    """Quadratischer Knopf nur mit Symbol (Material Icons) und Tooltip."""
    from PyQt6.QtCore import QSize as _QSize

    b = QPushButton()
    b.setObjectName("icon")
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setIcon(core.material_icon(icon, palette()["text"], 20))
    b.setIconSize(_QSize(20, 20))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b
