"""Auftraege und Schemas fuer die KI-Schritte (Bewertung, Gegenpruefung). Texte auf Deutsch, Abstracts bleiben englisch."""

from __future__ import annotations

from .europepmc import Paper

DESIGNS = ["systematic_review", "meta_analysis", "consensus", "guideline", "rct", "crossover_trial", "cohort",
           "observational", "review", "expert", "other"]
ACTIONS = ["new_card", "supports", "contradicts", "watch", "irrelevant"]
DIRECTNESS = ["direct", "indirect", "extrapolated"]

TRIAGE_SYSTEM = """Du bist wissenschaftlicher Assistent fuer ein Radsport-Trainingssystem. Du bewertest Abstracts von Studien fuer eine \
Wissensbasis, aus der ein KI-Trainer Empfehlungen fuer trainierte bis Elite-Radfahrer ableitet.

Strenge Regeln:
- Nutze ausschliesslich den uebergebenen Text. Ergaenze nichts aus dem Gedaechtnis und rate nicht. Steht eine Angabe nicht im Abstract, \
schreibe "unbekannt" bzw. null.
- quotes: 1 bis 3 woertliche, unveraenderte Auszuege aus dem Abstract (hoechstens 25 Woerter je Zitat), die den Befund stuetzen. \
Kopiere sie exakt, auch Zahlen und Satzzeichen. Erfinde keine Zitate.
- Alle anderen Textfelder schreibst Du in eigenen Worten auf Deutsch, knapp und sachlich.
- relevant = true nur, wenn die Studie eine handlungsrelevante Aussage zu Training, Ernaehrung, Umwelt oder Erholung fuer Ausdauer- \
bzw. Radsportler liefert. Studien an Patienten, Untrainierten oder fremden Themen sind nicht relevant.
- design: waehle nach dem Abstract (systematic_review, meta_analysis, consensus, guideline, rct, crossover_trial, cohort, \
observational, review, expert, other).
- directness: direct nur bei trainierten bis Elite-Radfahrern oder Ausdauersportlern; indirect bei anderen Populationen (z. B. Laeufer, \
Untrainierte, Aeltere, nur Frauen oder nur Maenner, wenn das Thema geschlechtsabhaengig ist); extrapolated bei Modellen und Schluessen ohne \
eigene Daten.
- suggested_action: new_card (neue Erkenntnis ohne passende Karte), supports (stuetzt eine vorhandene Karte, nenne target_card), \
contradicts (widerspricht einer vorhandenen Karte, nenne target_card), watch (interessant, aber zu schwach oder zu klein fuer eine \
Empfehlung), irrelevant.
- evidence_suggestion: A fuer Systematic Review, Metaanalyse oder Konsens mit klarer Aussage; B fuer randomisierte Studien oder Reviews mit \
Einschraenkungen; C fuer Beobachtungsstudien oder kleine Studien; nie D. Das System begrenzt die Stufe zusaetzlich (nur Abstract: hoechstens B).
- limitations: nenne kleine Stichprobe, kurze Dauer, Heterogenitaet, fehlende Kontrollgruppe, Interessenkonflikte, falsche Population, \
sofern aus dem Abstract erkennbar.
- card_draft nur bei new_card, sonst null. slug: kleinbuchstaben-mit-bindestrichen. summary hoechstens 300 Zeichen. recommendation als \
bedingte, handlungsnahe Regel ("Wenn ..., dann ...") hoechstens 600 Zeichen und nur mit Aussagen, die der Abstract traegt, ohne erfundene \
Zahlen. claims: je Aussage text (eigene Worte) und quote (woertlich aus dem Abstract, hoechstens 25 Woerter). Sei kritisch statt gefaellig."""

CROSS_SYSTEM = """Du pruefst die Auswertungen anderer Gutachter streng gegen den zugehoerigen Abstract. Nutze nur den uebergebenen Text.
Fuer jede Auswertung: verdict "ok", wenn alle Angaben (design, population, sample_n, summary, finding, limitations, directness und, falls \
vorhanden, der Kartenentwurf samt Empfehlung) vom Abstract gedeckt sind, sonst "issues". In issues nennst Du jede konkrete Abweichung: \
falsche oder erfundene Zahl, falsches Studiendesign, falsche Population, Aussage ohne Deckung im Abstract, Uebertreibung der Wirkung, \
fehlende wichtige Einschraenkung. Keine allgemeinen Floskeln."""

_STR = {"type": "string"}
_STR_NULL = {"type": ["string", "null"]}

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": _STR, "relevant": {"type": "boolean"}, "relevance_reason": _STR,
            "design": {"type": "string", "enum": DESIGNS}, "population": _STR,
            "sample_n": {"type": ["integer", "null"]}, "summary": _STR, "finding": _STR,
            "quotes": {"type": "array", "items": _STR}, "limitations": _STR,
            "directness": {"type": "string", "enum": DIRECTNESS},
            "suggested_action": {"type": "string", "enum": ACTIONS}, "target_card": _STR_NULL,
            "evidence_suggestion": {"type": "string", "enum": ["A", "B", "C"]},
            "card_draft": {"type": ["object", "null"], "properties": {
                "slug": _STR, "title": _STR, "tags": {"type": "array", "items": _STR}, "summary": _STR, "recommendation": _STR,
                "caveats": _STR_NULL,
                "applies_to": {"type": "object", "properties": {
                    "population": {"type": "array", "items": {"type": "string", "enum": ["elite", "trained", "recreational"]}},
                    "sex": {"type": "string", "enum": ["all", "female", "male"]}, "age": _STR_NULL}},
                "safety": {"type": "boolean"},
                "claims": {"type": "array", "items": {"type": "object", "properties": {"text": _STR, "quote": _STR},
                                                       "required": ["text", "quote"]}},
            }},
        },
        "required": ["id", "relevant", "relevance_reason", "design", "population", "summary", "finding", "quotes",
                     "limitations", "directness", "suggested_action", "evidence_suggestion"],
    }}},
    "required": ["results"],
}

CROSS_SCHEMA = {
    "type": "object",
    "properties": {"results": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": _STR, "verdict": {"type": "string", "enum": ["ok", "issues"]}, "issues": {"type": "array", "items": _STR}},
        "required": ["id", "verdict", "issues"],
    }}},
    "required": ["results"],
}


def paper_block(pid: str, p: Paper) -> str:
    return (f"[{pid}] Typ: {', '.join(p.pub_types) or 'unbekannt'} | Jahr: {p.year or '?'} | Journal: {p.journal or '?'}\n"
            f"Titel: {p.title}\nAbstract: {p.abstract}\n")


def triage_prompt(topic_label: str, existing: list[dict], papers: dict[str, Paper]) -> str:
    cards = "\n".join(f"- {c['slug']} | {c['title']} | Evidenz {c['evidence']}" for c in existing) or "- (noch keine)"
    blocks = "\n".join(paper_block(pid, p) for pid, p in papers.items())
    return (f"Thema: {topic_label}\n\nVorhandene Wissenskarten zu diesem Thema (Slug | Titel | Evidenz):\n{cards}\n\n"
            f"Bewerte jede der folgenden Studien. Gib je Studie genau ein Ergebnis mit der id aus der eckigen Klammer.\n\n{blocks}")


def cross_prompt(items: dict[str, tuple[Paper, dict]]) -> str:
    import json

    parts = []
    for pid, (p, ai) in items.items():
        keep = {k: ai.get(k) for k in ("design", "population", "sample_n", "summary", "finding", "limitations", "directness",
                                       "quotes", "card_draft") if k in ai}
        parts.append(f"[{pid}] Titel: {p.title}\nAbstract: {p.abstract}\nAuswertung (JSON): {json.dumps(keep, ensure_ascii=False)}\n")
    return "Pruefe jede Auswertung gegen ihren Abstract. Gib je Auswertung genau ein Ergebnis mit der id aus der eckigen Klammer.\n\n" + "\n".join(parts)
