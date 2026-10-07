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


def hr_tss(duration_s: float, avg_hr: float, hr_rest: float, hr_max: float, lthr: float) -> float:
    """Grobe HF-basierte TSS-Schaetzung (TRIMP-Verhaeltnis zur Stunde bei LTHR), falls keine Leistung vorliegt."""
    if hr_max <= hr_rest or duration_s <= 0:
        return 0.0
    from math import exp

    def trimp_per_min(hr: float) -> float:
        x = min(max((hr - hr_rest) / (hr_max - hr_rest), 0.0), 1.0)
        return x * 0.64 * exp(1.92 * x)

    hour_at_lthr = 60 * trimp_per_min(lthr)
    if hour_at_lthr <= 0:
        return 0.0
    return duration_s / 60 * trimp_per_min(avg_hr) / hour_at_lthr * 100


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
