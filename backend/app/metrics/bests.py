"""Einordnung von Bestleistungen (W/kg) nach dem Leistungsprofil aus Allen/Coggan, "Training and Racing with a Power Meter".

Die Tabelle gilt fuer Maenner. Die Stufen sind eine grobe Zuordnung der Coggan-Klassen auf die App-Begriffe:
Hobby = unter Cat 3, Amateur = Cat 3/2 (Good/Very Good), Elite = Cat 1 (Excellent),
Profi = Exceptional (Continental/Domestic Pro), Worldtour = World Class.
Zwischen den Stuetzstellen (5 s, 1 min, 5 min, 60 min) wird mit dem Critical-Power-Modell (ab 1 min) bzw. einem Potenzgesetz interpoliert.
"""

from __future__ import annotations

from math import log

LEVELS = ("hobby", "amateur", "elite", "pro", "worldtour")
LEVEL_LABELS = {"hobby": "Hobby", "amateur": "Amateur", "elite": "Elite", "pro": "Profi", "worldtour": "Worldtour"}

# Dauer (s) -> Mindest-W/kg fuer Amateur, Elite, Profi, Worldtour
_ANCHORS = {
    5: (15.4, 19.3, 21.0, 22.8),
    60: (7.7, 9.2, 9.9, 10.6),
    300: (4.2, 5.5, 6.2, 6.8),
    3600: (3.5, 4.6, 5.2, 5.6),
}
MIN_S, MAX_S = min(_ANCHORS), max(_ANCHORS)


def _between(lo: int, hi: int, d: int, p_lo: float, p_hi: float) -> float:
    """Leistung bei Dauer d zwischen zwei Stuetzstellen. Ab 1 min gilt das Critical-Power-Modell P = CP + W'/t
    (durch beide Stuetzstellen gelegt), darunter ein Potenzgesetz P = a * t^b, weil die Hyperbel dort zu steil abfaellt."""
    if lo >= 60:
        w = (p_lo - p_hi) / (1 / lo - 1 / hi)
        return p_hi - w / hi + w / d
    b = log(p_hi / p_lo) / log(hi / lo)
    return p_lo * (d / lo) ** b


def thresholds(duration_s: int) -> tuple[float, ...] | None:
    """Mindest-W/kg je Stufe (Amateur..Worldtour) fuer diese Dauer; None ausserhalb von 5 s bis 60 min."""
    if not MIN_S <= duration_s <= MAX_S:
        return None
    keys = sorted(_ANCHORS)
    hi = next(k for k in keys if k >= duration_s)
    lo = max(k for k in keys if k <= duration_s)
    if lo == hi:
        return _ANCHORS[lo]
    return tuple(_between(lo, hi, duration_s, a, b) for a, b in zip(_ANCHORS[lo], _ANCHORS[hi]))


def classify(duration_s: int, wkg: float) -> str | None:
    t = thresholds(duration_s)
    if t is None:
        return None
    return LEVELS[sum(wkg >= x for x in t)]
