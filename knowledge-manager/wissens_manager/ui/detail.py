"""Detailansichten aus Karten: Kandidat (Studie mit KI-Auswertung und Pruefungen) und Wissenskarte."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .. import topics
from .render import (ACTION_LABELS, CARD_STATUS_LABELS, DESIGN_LABELS, DIRECTNESS_LABELS, STATUS_LABELS, evidence_cap, found_on,
                     quote_summary)
from .widgets import (AMBER, BLUE, EVIDENCE_COLORS, GREEN, ORANGE, RED, SLATE, VIOLET, Card, Pill, bullet_list, label, link_label,
                      pill_row, status_row)

ACTION_COLORS = {"new_card": GREEN, "supports": BLUE, "contradicts": RED, "watch": AMBER, "irrelevant": SLATE}
DIRECTNESS_COLORS = {"direct": GREEN, "indirect": AMBER, "extrapolated": SLATE}
CARD_STATUS_COLORS = {"active": GREEN, "contested": ORANGE, "watch": AMBER, "retired": SLATE}
DECISION_COLORS = {"pending": BLUE, "accepted": GREEN, "watch": AMBER, "rejected": SLATE}


def _row(*widgets: QWidget, spacing: int = 10) -> QWidget:
    w = QWidget()
    w.setObjectName("plain")
    r = QHBoxLayout(w)
    r.setContentsMargins(0, 0, 0, 0)
    r.setSpacing(spacing)
    for x in widgets:
        r.addWidget(x)
    r.addStretch(1)
    return w


def _stack(*widgets: QWidget, spacing: int = 4) -> QWidget:
    w = QWidget()
    w.setObjectName("plain")
    c = QVBoxLayout(w)
    c.setContentsMargins(0, 0, 0, 0)
    c.setSpacing(spacing)
    for x in widgets:
        c.addWidget(x)
    return w


def _text_card(title: str, text: str | None, *, muted: bool = False) -> Card | None:
    if not text:
        return None
    card = Card(title)
    card.add(label(text, "muted" if muted else "body", selectable=True))
    return card


# ------------------------------------------------------------- Kandidat ---


def candidate_widgets(c: dict, *, new: bool = False) -> list[QWidget]:
    a = c.get("analysis") or {}
    paper, ai, chk = a.get("paper") or {}, a.get("ai") or {}, a.get("check") or {}
    out: list[QWidget] = []

    # Kopf: Studie
    head = Card(spacing=8)
    over = " · ".join(x for x in ("STUDIE", DESIGN_LABELS.get(ai.get("design"), "").upper(), str(paper.get("year") or "")) if x)
    head.add(label(over, "overline2", wrap=False))
    head.add(label(c["title"], "h2", selectable=True))
    if paper.get("authors"):
        head.add(label(paper["authors"], "small", selectable=True))
    where = " · ".join(x for x in (paper.get("journal"), str(paper.get("year") or "")) if x)
    if paper.get("url"):
        head.add(_row(label(where, "small", wrap=False), link_label(paper.get("doi") or "Zur Studie", paper["url"])))
    elif where:
        head.add(label(where, "small"))
    pills: list[tuple[str, str]] = []
    if new:
        pills.append(("NEU", GREEN))
    pills.append((topics.topic_label(c.get("topic", "")), VIOLET))
    if ai.get("sample_n"):
        pills.append((f"n = {ai['sample_n']}", BLUE))
    if ai.get("directness"):
        pills.append((DIRECTNESS_LABELS.get(ai["directness"], ai["directness"]), DIRECTNESS_COLORS.get(ai["directness"], SLATE)))
    pills.append((STATUS_LABELS.get(c.get("status"), c.get("status", "")), DECISION_COLORS.get(c.get("status"), SLATE)))
    if when := found_on(c):
        pills.append((f"gefunden {when}", SLATE))
    head.add(pill_row(pills))
    if ai.get("population"):
        head.add(_stack(label("Population", "caption"), label(ai["population"], "body", selectable=True)))
    out.append(head)

    # Vorschlag der KI
    action = ai.get("suggested_action")
    sug = Card("Vorschlag der KI")
    sug.add(_row(Pill(ACTION_LABELS.get(action, "—"), ACTION_COLORS.get(action, SLATE)),
                 *( [label(f"Karte: {ai['target_card']}", "small", wrap=False)] if ai.get("target_card") else [])))
    if ai.get("relevance_reason"):
        sug.add(label(ai["relevance_reason"], "muted", selectable=True))
    if ai.get("evidence_suggestion"):
        cap = evidence_cap((a.get("suggested_source") or {}).get("basis"))
        sug.add(label(f"Evidenzvorschlag der KI: {ai['evidence_suggestion']}. Mit nur geprüftem Abstract erlaubt das Backend höchstens {cap}.",
                      "small"))
    out.append(sug)

    # Pruefungen
    q_state, q_text = quote_summary(chk)
    cross = chk.get("cross_check") or {}
    retr = chk.get("retraction") or {}
    checks = Card("Prüfungen", spacing=8)
    checks.add(status_row(q_state, q_text))
    checks.add(status_row({"ok": True, "issues": False}.get(cross.get("verdict")),
                          {"ok": "Gegenprüfung durch die KI: keine Abweichungen",
                           "issues": "Gegenprüfung durch die KI: Abweichungen gefunden"}.get(cross.get("verdict"), "Gegenprüfung nicht durchgeführt")))
    checks.add(status_row({"ok": True, "retracted": False}.get(retr.get("status")), retr.get("reason") or "Rückzug nicht geprüft"))
    checks.add(status_row(chk.get("metadata_ok"), "Titel und Jahr stimmen mit Crossref überein" if chk.get("metadata_ok") is not False
                          else "Titel oder Jahr weichen von Crossref ab"))
    out.append(checks)
    if cross.get("issues"):
        warn = Card("Abweichungen laut Gegenprüfung", "Vor dem Aufnehmen prüfen und im Kartenentwurf korrigieren.", tone=RED)
        warn.add(bullet_list([str(i) for i in cross["issues"]], RED))
        out.append(warn)

    if ai.get("summary") or ai.get("finding"):
        sm = Card("Zusammenfassung der KI")
        if ai.get("summary"):
            sm.add(label(ai["summary"], "body", selectable=True))
        if ai.get("finding"):
            sm.add(_stack(label("Befund", "caption"), label(ai["finding"], "body", selectable=True)))
        out.append(sm)
    quotes = chk.get("quotes") or []
    if quotes:
        qc = Card("Belegzitate", "Müssen wörtlich im Abstract stehen", spacing=8)
        for q in quotes:
            qc.add(status_row(q["found"], f"„{q['quote']}“"))
        out.append(qc)
    if card := _text_card("Grenzen", ai.get("limitations")):
        out.append(card)
    draft = ai.get("card_draft")
    if draft:
        dc = Card("Kartenentwurf")
        dc.add(label(draft.get("title") or "", "h3", selectable=True))
        if draft.get("slug"):
            dc.add(label(draft["slug"], "small"))
        if draft.get("recommendation"):
            dc.add(label(draft["recommendation"], "body", selectable=True))
        out.append(dc)
    if c.get("decision_note"):
        out.append(_text_card(f"Entscheidung: {STATUS_LABELS.get(c['status'], c['status'])}", c["decision_note"]))
    if ab := _text_card("Abstract", paper.get("abstract"), muted=True):
        out.append(ab)
    return out


# --------------------------------------------------------- Wissenskarte ---


def card_widgets(card: dict) -> list[QWidget]:
    out: list[QWidget] = []
    head = Card(spacing=8)
    head.add(label(f"WISSENSKARTE · {(card.get('topic_label') or '').upper()}", "overline2", wrap=False))
    head.add(label(card["title"], "h2", selectable=True))
    head.add(label(card["slug"], "small", selectable=True))
    ev = card.get("evidence")
    pills = [(f"Evidenz {ev}", EVIDENCE_COLORS.get(ev, SLATE)),
             (DIRECTNESS_LABELS.get(card.get("directness"), card.get("directness") or ""), DIRECTNESS_COLORS.get(card.get("directness"), SLATE)),
             (CARD_STATUS_LABELS.get(card.get("status"), card.get("status") or ""), CARD_STATUS_COLORS.get(card.get("status"), SLATE))]
    if card.get("safety"):
        pills.append(("sicherheitsrelevant", RED))
    if card.get("review_overdue"):
        pills.append((f"Überprüfung fällig seit {card.get('review_due')}", RED))
    head.add(pill_row(pills))
    out.append(head)

    if rec := _text_card("Empfehlung", card.get("recommendation")):
        out.append(rec)
    if s := _text_card("Kurz gesagt", card.get("summary")):
        out.append(s)
    ap = card.get("applies_to") or {}
    pops = {"elite": "Elite", "trained": "Trainierte", "recreational": "Freizeit"}
    sexes = {"all": "alle Geschlechter", "female": "Frauen", "male": "Männer"}
    applies = [(pops.get(p, p), BLUE) for p in ap.get("population") or []] + [(sexes.get(ap.get("sex"), ap.get("sex") or "alle"), VIOLET)]
    if ap.get("age"):
        applies.append((f"Alter {ap['age']}", SLATE))
    ga = Card("Gilt für")
    ga.add(pill_row(applies))
    out.append(ga)
    if cv := _text_card("Grenzen", card.get("caveats")):
        out.append(cv)
    for p in card.get("positions") or []:
        pc = Card(f"Position: {p['label']}")
        pc.add(label(p.get("summary") or "", "body", selectable=True))
        pc.add(label("Quellen: " + ", ".join(p.get("source_keys") or []), "small"))
        out.append(pc)
    if card.get("claims"):
        cl = Card("Belegte Aussagen", spacing=14)
        for c in card["claims"]:
            cl.add(_stack(label(c.get("text") or "", "body", selectable=True),
                          label(f"„{c.get('quote')}“", "muted", selectable=True),
                          label(c.get("citation") or c.get("source_key") or "", "small")))
        out.append(cl)
    if card.get("sources"):
        sc = Card("Quellen", spacing=14)
        for s in card["sources"]:
            meta = " · ".join(x for x in (s.get("design_label") or DESIGN_LABELS.get(s.get("design"), ""),
                                          f"n = {s['sample_n']}" if s.get("sample_n") else "",
                                          "nur Abstract" if s.get("basis") == "abstract" else "Volltext") if x)
            parts = [label(s.get("citation") or s.get("key") or "", "h3"), label(s.get("title") or "", "body", selectable=True),
                     label(meta, "small")]
            if s.get("url"):
                parts.append(link_label(s.get("doi") or "Zur Studie", s["url"]))
            sc.add(_stack(*parts))
        out.append(sc)
    out.append(label(f"Version {card.get('version')} · geprüft am {card.get('reviewed')} · Überprüfung bis {card.get('review_due')}", "small"))
    return out
