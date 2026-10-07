"""HTML-Darstellung von Kandidaten und Karten (reine Funktionen, ohne Qt, gut testbar)."""

from __future__ import annotations

import html

from .. import topics

ACTION_LABELS = {
    "new_card": "Neue Karte vorgeschlagen",
    "supports": "Stützt eine vorhandene Karte",
    "contradicts": "Widerspricht einer vorhandenen Karte",
    "watch": "Nur beobachten (Watchlist)",
    "irrelevant": "Nicht relevant",
}
DESIGN_LABELS = {
    "systematic_review": "Systematic Review", "meta_analysis": "Metaanalyse", "consensus": "Konsens-Statement", "guideline": "Leitlinie",
    "rct": "RCT", "crossover_trial": "Crossover-Studie", "cohort": "Kohortenstudie", "observational": "Beobachtungsstudie",
    "review": "Übersichtsarbeit", "expert": "Expertenmeinung", "other": "Sonstige",
}
DIRECTNESS_LABELS = {"direct": "direkt übertragbar", "indirect": "indirekt (andere Population)", "extrapolated": "extrapoliert"}
EVIDENCE_LABELS = {"A": "A · starke Evidenz", "B": "B · moderate Evidenz", "C": "C · schwache Evidenz", "D": "D · Expertenpraxis"}
STATUS_LABELS = {"pending": "Offen", "accepted": "Aufgenommen", "watch": "Watchlist", "rejected": "Verworfen"}
CARD_STATUS_LABELS = {"active": "Aktiv", "contested": "Umstritten", "watch": "Watchlist", "retired": "Stillgelegt"}
OK, BAD, UNKNOWN = "#16a34a", "#dc2626", "#94a3b8"
# Gleiche Farben wie die Evidenz-Chips der App (knowledge_sources.dart)
EVIDENCE_COLORS = {"A": "#16a34a", "B": "#3b82f6", "C": "#f59e0b", "D": "#64748b"}


def esc(v: object) -> str:
    return html.escape("" if v is None else str(v))


def light(state: bool | None, text: str) -> str:
    color, mark = (OK, "✓") if state is True else (BAD, "✗") if state is False else (UNKNOWN, "–")
    return f'<span style="color:{color};font-weight:bold">{mark}</span> {esc(text)}'


def evidence_cap(basis: str | None) -> str:
    """Hoechste Stufe, die das Backend fuer diese Quellenbasis zulaesst (nur Abstract: B)."""
    return "A" if basis == "fulltext" else "B"


def quote_summary(checks: dict) -> tuple[bool | None, str]:
    qs = (checks.get("quotes") or []) + (checks.get("claim_quotes") or [])
    if not qs:
        return None, "Keine Belegzitate geliefert"
    missing = [q for q in qs if not q["found"]]
    if not missing:
        return True, f"Alle {len(qs)} Belegzitate stehen wörtlich im Abstract"
    return False, f"{len(missing)} von {len(qs)} Belegzitaten stehen NICHT im Abstract"


def found_on(c: dict) -> str:
    """Funddatum (TT.MM.) aus created_at, leer wenn unbekannt."""
    raw = str(c.get("created_at") or "")
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        return f"{raw[8:10]}.{raw[5:7]}."
    return ""


def candidate_title(c: dict, new: bool = False) -> str:
    a = c.get("analysis") or {}
    ai = a.get("ai") or {}
    paper = a.get("paper") or {}
    flags = ""
    chk = a.get("check") or {}
    if (chk.get("retraction") or {}).get("status") == "retracted":
        flags += " ⚠ zurückgezogen"
    elif (chk.get("cross_check") or {}).get("verdict") == "issues" or quote_summary(chk)[0] is False:
        flags += " ⚠ prüfen"
    when = found_on(c)
    meta = " · ".join(x for x in (topics.topic_label(c["topic"]), str(paper.get("year") or "?"),
                                  ACTION_LABELS.get(ai.get("suggested_action"), "—")) if x)
    if new:
        return f"NEU · {c['title']}\n{meta}{flags}"
    return f"{c['title']}\n{meta}{flags}" + (f" · gefunden {when}" if when else "")


def candidate_html(c: dict) -> str:
    a = c.get("analysis") or {}
    paper, ai, chk = a.get("paper") or {}, a.get("ai") or {}, a.get("check") or {}
    q_state, q_text = quote_summary(chk)
    cross = chk.get("cross_check") or {}
    retr = chk.get("retraction") or {}
    out = [f"<h2>{esc(c['title'])}</h2>"]
    out.append(f"<p style='color:{UNKNOWN}'>{esc(paper.get('authors'))}<br>{esc(paper.get('journal'))} {esc(paper.get('year'))}"
               + (f" · <a href='{esc(paper.get('url'))}'>{esc(paper.get('doi') or 'Link')}</a>" if paper.get("url") else "") + "</p>")
    meta = [DESIGN_LABELS.get(ai.get("design"), ""), ai.get("population"), f"n = {ai['sample_n']}" if ai.get("sample_n") else "",
            DIRECTNESS_LABELS.get(ai.get("directness"), ""), ", ".join(paper.get("pub_types") or [])]
    out.append(f"<p><b>{esc(' · '.join(m for m in meta if m))}</b></p>")
    out.append(f"<p><b>KI-Vorschlag:</b> {esc(ACTION_LABELS.get(ai.get('suggested_action'), '—'))}"
               + (f" → Karte <code>{esc(ai.get('target_card'))}</code>" if ai.get("target_card") else "") + "</p>")
    if ai.get("relevance_reason"):
        out.append(f"<p><i>{esc(ai['relevance_reason'])}</i></p>")
    out.append("<h3>Prüfungen</h3><p>"
               + "<br>".join([light(q_state, q_text), light({"ok": True, "issues": False}.get(cross.get("verdict")),
                                                            {"ok": "Gegenprüfung durch die KI: keine Abweichungen",
                                                             "issues": "Gegenprüfung durch die KI: Abweichungen gefunden"}.get(
                                                                cross.get("verdict"), "Gegenprüfung nicht durchgeführt")),
                              light({"ok": True, "retracted": False}.get(retr.get("status")), retr.get("reason") or "Rückzug nicht geprüft"),
                              light(chk.get("metadata_ok"), "Titel und Jahr stimmen mit Crossref überein" if chk.get("metadata_ok") is not False
                                    else "Titel oder Jahr weichen von Crossref ab")]) + "</p>")
    if cross.get("issues"):
        out.append("<ul>" + "".join(f"<li style='color:{BAD}'>{esc(i)}</li>" for i in cross["issues"]) + "</ul>")
    if ai.get("summary"):
        out.append(f"<h3>Zusammenfassung (KI)</h3><p>{esc(ai['summary'])}</p>")
    if ai.get("finding"):
        out.append(f"<h3>Befund</h3><p>{esc(ai['finding'])}</p>")
    if chk.get("quotes"):
        out.append("<h3>Belegzitate</h3><ul>" + "".join(f"<li>{light(q['found'], '„' + q['quote'] + '“')}</li>" for q in chk["quotes"]) + "</ul>")
    if ai.get("limitations"):
        out.append(f"<h3>Grenzen</h3><p>{esc(ai['limitations'])}</p>")
    draft = ai.get("card_draft")
    if draft:
        basis = (a.get("suggested_source") or {}).get("basis")
        out.append(f"<h3>Kartenentwurf</h3><p><b>{esc(draft.get('title'))}</b> <code>{esc(draft.get('slug'))}</code><br>{esc(draft.get('recommendation'))}</p>"
                   f"<p>Evidenzvorschlag der KI: <b>{esc(ai.get('evidence_suggestion'))}</b>; mit nur geprüftem Abstract erlaubt das Backend höchstens "
                   f"<b>{evidence_cap(basis)}</b>.</p>")
    if c.get("decision_note"):
        out.append(f"<h3>Entscheidung</h3><p>{esc(STATUS_LABELS.get(c['status'], c['status']))}: {esc(c['decision_note'])}</p>")
    if paper.get("abstract"):
        out.append(f"<h3>Abstract</h3><p style='color:{UNKNOWN}'>{esc(paper['abstract'])}</p>")
    return "".join(out)


def card_html(card: dict) -> str:
    out = [f"<h2>{esc(card['title'])}</h2><p><code>{esc(card['slug'])}</code> · {esc(card.get('topic_label'))} · "
           f"<b style='color:{EVIDENCE_COLORS.get(card['evidence'], UNKNOWN)}'>{esc(EVIDENCE_LABELS.get(card['evidence']))}</b> · {esc(DIRECTNESS_LABELS.get(card['directness']))} · "
           f"{esc(CARD_STATUS_LABELS.get(card['status'], card['status']))}"
           + (" · <b style='color:#dc2626'>sicherheitsrelevant</b>" if card.get("safety") else "") + "</p>"]
    if card.get("review_overdue"):
        out.append(f"<p style='color:{BAD}'><b>Überprüfung fällig</b> seit {esc(card.get('review_due'))}</p>")
    out.append(f"<h3>Empfehlung</h3><p>{esc(card['recommendation'])}</p><h3>Kurz gesagt</h3><p>{esc(card['summary'])}</p>")
    ap = card.get("applies_to") or {}
    out.append(f"<p><b>Gilt für:</b> {esc(', '.join(ap.get('population') or []) or '—')} · {esc(ap.get('sex'))} · {esc(ap.get('age') or '—')}</p>")
    if card.get("caveats"):
        out.append(f"<h3>Grenzen</h3><p>{esc(card['caveats'])}</p>")
    for p in card.get("positions") or []:
        out.append(f"<p><b>{esc(p['label'])}:</b> {esc(p['summary'])} <i>({esc(', '.join(p['source_keys']))})</i></p>")
    if card.get("claims"):
        out.append("<h3>Belegte Aussagen</h3><ul>" + "".join(
            f"<li>{esc(c.get('text'))}<br><i>„{esc(c.get('quote'))}“ ({esc(c.get('citation') or c.get('source_key'))})</i></li>"
            for c in card["claims"]) + "</ul>")
    if card.get("sources"):
        out.append("<h3>Quellen</h3><ul>" + "".join(
            f"<li><b>{esc(s.get('citation') or s.get('key'))}</b> {esc(s.get('title'))} · "
            f"{esc(s.get('design_label') or DESIGN_LABELS.get(s.get('design'), ''))}"
            + (f" · n = {esc(s['sample_n'])}" if s.get("sample_n") else "") + (" · nur Abstract" if s.get("basis") == "abstract" else " · Volltext")
            + (f" · <a href='{esc(s['url'])}'>Link</a>" if s.get("url") else "") + "</li>" for s in card["sources"]) + "</ul>")
    out.append(f"<p style='color:{UNKNOWN}'>Version {esc(card.get('version'))} · geprüft am {esc(card.get('reviewed'))} · Überprüfung bis {esc(card.get('review_due'))}</p>")
    return "".join(out)
