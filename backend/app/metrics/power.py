"""Reine Leistungsmetriken (NP, IF, TSS, hrTSS, Zonen). Keine DB- oder I/O-Abhaengigkeit."""

from __future__ import annotations

from collections.abc import Sequence
from math import sqrt

# Coggan-Leistungszonen als Anteil der FTP: (Name, untere Grenze, obere Grenze)
POWER_ZONES = [
    ("Z1 Aktive Erholung", 0.0, 0.55),
    ("Z2 Ausdauer", 0.55, 0.75),
    ("Z3 Tempo", 0.75, 0.90),
    ("Z4 Schwelle", 0.90, 1.05),
    ("Z5 VO2max", 1.05, 1.20),
    ("Z6 Anaerob", 1.20, 1.50),
    ("Z7 Neuromuskulaer", 1.50, float("inf")),
]


def power_zones(ftp: float) -> list[dict]:
    return [
        {"name": n, "min": round(lo * ftp), "max": None if hi == float("inf") else round(hi * ftp)}
        for n, lo, hi in POWER_ZONES
    ]


def normalized_power(watts: Sequence[float], sample_rate_s: float = 1.0) -> float:
    """NP: 30-s gleitender Mittelwert, 4. Potenz, Mittel, 4. Wurzel."""
    window = max(1, round(30 / sample_rate_s))
    n = len(watts)
    if n < window:
        return 0.0
    total = sum(watts[:window])
    acc = 0.0
    count = 0
    for i in range(window, n + 1):
        acc += (total / window) ** 4
        count += 1
        if i < n:
            total += watts[i] - watts[i - window]
    return (acc / count) ** 0.25


def intensity_factor(np_watts: float, ftp: float) -> float:
    return np_watts / ftp if ftp > 0 else 0.0


def tss(duration_s: float, np_watts: float, ftp: float) -> float:
    if ftp <= 0 or duration_s <= 0:
        return 0.0
    if_ = np_watts / ftp
    return duration_s * np_watts * if_ / (ftp * 3600) * 100


# hrTSS wie bei TrainingPeaks: Zeit in Herzfrequenzzonen (bezogen auf die Schwellenherzfrequenz LTHR) mal TSS je Stunde der Zone.
# Zonengrenzen in % der LTHR nach Joe Friel (Rad / Laufen); eine Stunde in Zone 5a entspricht 100 TSS (Beispiel in der
# TrainingPeaks-Hilfe). Die uebrigen Stundenwerte sind eine Annaeherung, TrainingPeaks veroeffentlicht die Tabelle nicht.
HR_ZONE_BOUNDS = {"bike": (81, 90, 94, 100, 103, 107), "run": (85, 90, 95, 100, 103, 107)}
HR_ZONE_TSS_PER_HOUR = (20, 40, 60, 80, 100, 120, 140)  # Z1, Z2, Z3, Z4, Z5a, Z5b, Z5c


def hr_zone_index(hr: float, lthr: float, kind: str = "bike") -> int:
    pct = hr / lthr * 100
    return sum(pct >= b for b in HR_ZONE_BOUNDS[kind])


def hr_tss(duration_s: float, avg_hr: float, lthr: float, kind: str = "bike") -> float:
    """hrTSS aus der Durchschnittsherzfrequenz (Naeherung, wenn keine Herzfrequenzkurve vorliegt)."""
    if lthr <= 0 or duration_s <= 0 or avg_hr <= 0:
        return 0.0
    return duration_s / 3600 * HR_ZONE_TSS_PER_HOUR[hr_zone_index(avg_hr, lthr, kind)]


def hr_tss_series(time_s: Sequence[float], hr: Sequence[float | None], lthr: float, kind: str = "bike", max_gap_s: float = 10) -> float:
    """hrTSS aus der Herzfrequenzkurve: jede Sekunde zaehlt mit dem Stundenwert ihrer Zone, Luecken ueber max_gap_s nicht."""
    if lthr <= 0 or len(time_s) < 2:
        return 0.0
    total = 0.0
    for i in range(len(time_s) - 1):
        v = hr[i] if i < len(hr) else None
        if not v or v <= 0:
            continue
        dt = min(time_s[i + 1] - time_s[i], max_gap_s)
        if dt > 0:
            total += dt / 3600 * HR_ZONE_TSS_PER_HOUR[hr_zone_index(v, lthr, kind)]
    return total


def effective_lthr(lthr: float | None, hr_max: float | None) -> float | None:
    """Schwellenherzfrequenz aus dem Profil; fehlt sie, wird sie als 90 % der maximalen Herzfrequenz geschaetzt."""
    if lthr:
        return float(lthr)
    return round(hr_max * 0.9) if hr_max else None


def mean_max_power(watts: Sequence[float], durations_s: Sequence[int]) -> dict[int, float]:
    """Beste Durchschnittsleistung je Dauer (1-Hz-Daten)."""
    out: dict[int, float] = {}
    n = len(watts)
    for d in durations_s:
        if d > n or d <= 0:
            continue
        s = sum(watts[:d])
        best = s
        for i in range(d, n):
            s += watts[i] - watts[i - d]
            best = max(best, s)
        out[d] = best / d
    return out


def mean_max_curve(watts: Sequence[float], durations_s: Sequence[int]) -> list[dict]:
    """Beste Durchschnittsleistung je Dauer mit Startsekunde des besten Abschnitts (1-Hz-Daten)."""
    n = len(watts)
    prefix = [0.0]
    for w in watts:
        prefix.append(prefix[-1] + w)
    out = []
    for d in durations_s:
        if d <= 0 or d > n:
            continue
        start = max(range(n - d + 1), key=lambda i: prefix[i + d] - prefix[i])
        out.append({"duration_s": d, "watts": round((prefix[start + d] - prefix[start]) / d, 1), "start_s": start})
    return out


def variability_index(np_watts: float, avg_watts: float) -> float:
    return np_watts / avg_watts if avg_watts > 0 else 0.0


def stddev(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return sqrt(sum((v - m) ** 2 for v in values) / len(values))
