"""Themen der Wissensbasis (Schluessel wie im Backend) mit Standard-Suchanfragen fuer Europe PMC.

Die Begriffe sind auf Titel und Abstract beschraenkt (TITLE_ABS), weil lose Begriffe auch Volltexte treffen und
thematisch Unpassendes liefern. Reste filtert die KI-Bewertung heraus.
"""

from __future__ import annotations

TOPICS: dict[str, tuple[str, str]] = {
    "intervalle": (
        "Intervalle",
        'TITLE_ABS:("interval training" OR HIIT OR "high-intensity interval" OR "sprint interval") '
        'AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes" OR "endurance-trained")',
    ),
    "zonen": (
        "Zonenmodelle und Tests",
        'TITLE_ABS:("critical power" OR "functional threshold power" OR "intensity domains" OR "training zones" '
        'OR "lactate threshold" OR "maximal lactate steady state" OR "ramp test") '
        'AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes")',
    ),
    "periodisierung": (
        "Training und Periodisierung",
        'TITLE_ABS:("training intensity distribution" OR polarized OR polarised OR pyramidal OR periodization OR '
        'periodisation OR "block periodization" OR "training load") AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes")',
    ),
    "tapering": (
        "Tapering und Wettkampf",
        'TITLE_ABS:(taper OR tapering) AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes" OR endurance)',
    ),
    "ernaehrung": (
        "Ernährung und Energie",
        'TITLE_ABS:("carbohydrate intake" OR "carbohydrate ingestion" OR "low energy availability" OR RED-S OR '
        'fueling OR caffeine OR hydration OR "periodized nutrition") AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes")',
    ),
    "kraft": (
        "Kraft",
        'TITLE_ABS:("strength training" OR "resistance training" OR "heavy strength") AND TITLE_ABS:(cycling OR cyclists OR '
        '"endurance athletes" OR "endurance performance")',
    ),
    "hitze": (
        "Hitze",
        'TITLE_ABS:("heat acclimation" OR "heat acclimatization" OR "heat training" OR "heat stress") '
        'AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes" OR endurance)',
    ),
    "hoehe": (
        "Höhe",
        'TITLE_ABS:(altitude OR hypoxia OR hypoxic) AND TITLE_ABS:("live high" OR "altitude training" OR "endurance athletes" '
        'OR cycling OR cyclists)',
    ),
    "frauen": (
        "Frauen",
        'TITLE_ABS:("menstrual cycle" OR "oral contraceptive" OR "female athletes" OR "women athletes" OR "sex differences") '
        'AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes" OR endurance)',
    ),
    "masters": (
        "Masters",
        'TITLE_ABS:("masters athletes" OR "older athletes" OR "older cyclists" OR "veteran athletes" OR "master cyclists") '
        'AND TITLE_ABS:(training OR endurance OR cycling OR performance)',
    ),
    "erholung": (
        "Erholung und Monitoring",
        'TITLE_ABS:(recovery OR "heart rate variability" OR overreaching OR overtraining OR "acute chronic workload" OR '
        '"training monitoring") AND TITLE_ABS:(cycling OR cyclists OR "endurance athletes")',
    ),
    "sonstiges": ("Sonstiges", ""),
}

# Studientypen: Anzeigename -> Europe-PMC-Werte fuer PUB_TYPE
STUDY_TYPES: dict[str, tuple[str, list[str]]] = {
    "reviews": ("Systematic Reviews und Metaanalysen", ["Systematic Review", "Meta-Analysis"]),
    "guidelines": ("Leitlinien und Konsens-Statements", ["Practice Guideline", "Consensus Statement", "Guideline"]),
    "trials": ("Randomisierte Studien", ["Randomized Controlled Trial"]),
}
DEFAULT_STUDY_TYPES = ("reviews", "guidelines")


def topic_label(key: str) -> str:
    return TOPICS.get(key, (key, ""))[0]


def build_query(topic: str, free_text: str = "", study_types: tuple[str, ...] = DEFAULT_STUDY_TYPES, year_from: int | None = None) -> str:
    """Europe-PMC-Suchanfrage: Thema oder freie Frage, Studientypen, ab Jahr, nur indexierte Fachartikel (keine Preprints)."""
    core = free_text.strip() or TOPICS.get(topic, ("", ""))[1]
    if not core:
        raise ValueError("Bitte ein Thema mit Standardanfrage oder eine eigene Suchanfrage angeben")
    types = [t for key in study_types for t in STUDY_TYPES[key][1]]
    parts = [f"({core})"]
    if types:
        parts.append("(" + " OR ".join(f'PUB_TYPE:"{t}"' for t in types) + ")")
    if year_from:
        parts.append(f"PUB_YEAR:[{year_from} TO 3000]")
    parts.append("SRC:MED")  # Preprints und nicht indexierte Quellen bleiben aussen vor
    return " AND ".join(parts)
