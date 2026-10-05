"""Analyse einzelner Fahrten, der Trainingsbelastung und der FTP. Reine Funktionen ohne DB oder I/O.

Die Schwellen hier sind Praxisregeln (Coggan/TrainingPeaks, Foster), keine Studienergebnisse. Sie liefern
Hinweise mit Begruendung; die Einordnung fuer den Athleten uebernimmt der Coach.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence

from .power import POWER_ZONES, mean_max_power, normalized_power, stddev
from .workout import Leaf, Repeat, flatten

METRICS_VERSION = 1  # erhoehen, wenn sich die Berechnung aendert (gespeicherte Werte werden dann neu berechnet)
MMP_DURATIONS = (5, 15, 60, 180, 300, 480, 600, 1200, 1800, 3600)
MMP_LABELS = {5: "5 s", 15: "15 s", 60: "1 min", 180: "3 min", 300: "5 min", 480: "8 min", 600: "10 min",
              1200: "20 min", 1800: "30 min", 3600: "60 min"}
EFFORT_PCT = 0.88  # ab Sweetspot zaehlt ein Abschnitt als Belastung
EFFORT_MIN_S = 30
RIDE_TYPES = {
    "race": "Rennen", "recovery": "Erholung", "endurance": "Grundlage", "tempo": "Tempo/Sweetspot",
    "threshold": "Schwelle", "vo2max": "VO2max", "anaerobic": "Anaerob/Sprint", "mixed": "Gemischt",
    "race_like": "Rennaehnlich (viele Antritte)",
}
RACE_WORDS = re.compile(
    r"\b(rennen|race|crit|kriterium|zeitfahren|einzelzeitfahren|itt|granfondo|gran fondo|marathon|rundfahrt|etappe|"
    r"stage|meisterschaft|championship|radrennen|bergrennen|cup|classic|klassiker)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------- Hilfen ---


def _avg(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def rolling(values: Sequence[float], window: int) -> list[float]:
    """Gleitender Mittelwert (zentriert am Fensterende), gleiche Laenge wie die Eingabe."""
    out: list[float] = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= window:
            s -= values[i - window]
        out.append(s / min(i + 1, window))
    return out


def zone_seconds(watts: Sequence[float], ftp: float) -> list[int]:
    secs = [0] * len(POWER_ZONES)
    if ftp <= 0:
        return secs
    for w in watts:
        pct = w / ftp
        for i in range(len(POWER_ZONES) - 1, -1, -1):
            if pct >= POWER_ZONES[i][1]:
                secs[i] += 1
                break
    return secs


def detect_efforts(watts: Sequence[float], ftp: float, min_s: int = EFFORT_MIN_S, pct: float = EFFORT_PCT) -> list[dict]:
    """Zusammenhaengende Abschnitte ueber pct x FTP (10-s-geglaettet, Luecken bis 10 s werden ueberbrueckt)."""
    if ftp <= 0 or not watts:
        return []
    trailing = rolling(watts, 10)
    n = len(trailing)
    smooth = [trailing[min(i + 5, n - 1)] for i in range(n)]  # zentriert, damit die Grenzen nicht nachlaufen
    limit = ftp * pct
    raw: list[list[int]] = []
    start = None
    for i, w in enumerate(smooth):
        if w >= limit and start is None:
            start = i
        elif w < limit and start is not None:
            raw.append([start, i])
            start = None
    if start is not None:
        raw.append([start, len(smooth)])
    merged: list[list[int]] = []
    for seg in raw:
        if merged and seg[0] - merged[-1][1] <= 10:
            merged[-1][1] = seg[1]
        else:
            merged.append(seg)
    out = []
    for a, b in merged:
        if b - a < min_s:
            continue
        avg = _avg(watts[a:b])
        out.append({"start_s": a, "duration_s": b - a, "avg_w": round(avg), "pct_ftp": round(avg / ftp * 100)})
    return out


def is_race(name: str | None, workout_type: int | None, event_on_day: bool, intensity: float | None) -> bool:
    """Strava markiert Rennen mit workout_type 11. Sonst: Event im Saisonplan am Tag oder Rennbegriff im Namen bei hoher Intensitaet."""
    if workout_type == 11 or event_on_day:
        return True
    return bool(name and RACE_WORDS.search(name) and (intensity or 0) >= 0.8)


def classify(zones_s: Sequence[int], intensity: float | None, efforts: Sequence[dict], race: bool, matches: int = 0) -> str:
    if race:
        return "race"
    if intensity is not None and intensity < 0.62:
        return "recovery"
    z = list(zones_s) + [0] * (7 - len(zones_s))
    if sum(z) >= 3600 and (intensity or 0) >= 0.85 and matches >= 15:
        return "race_like"  # lang, hart, viele Antritte: Rennen oder harte Gruppenfahrt
    hard = [e for e in efforts if e["pct_ftp"] >= 106]
    vo2_time = sum(e["duration_s"] for e in hard if e["duration_s"] >= 120)
    if z[5] + z[6] >= 180 and vo2_time < 360:
        return "anaerobic"
    if vo2_time >= 360:
        return "vo2max"
    if sum(e["duration_s"] for e in efforts if 94 <= e["pct_ftp"] < 106) >= 900:
        return "threshold"
    if sum(e["duration_s"] for e in efforts if e["pct_ftp"] < 94) + z[2] >= 1200:
        return "tempo"
    if intensity is not None and intensity >= 0.85:
        return "mixed"
    return "endurance"


# ------------------------------------------------------- Einzelne Fahrt ---


def ride_metrics(watts: Sequence[float] | None, hr: Sequence[float] | None, ftp: float, *,
                 cadence: Sequence[float] | None = None, duration_s: int | None = None) -> dict:
    """Kennzahlen aus 1-Hz-Reihen (Watt, Puls, Kadenz). Fehlende Reihen fuehren zu fehlenden Feldern."""
    out: dict = {"version": METRICS_VERSION, "ftp_used": ftp}
    watts = [float(w or 0) for w in (watts or [])]
    hr = [float(h or 0) for h in (hr or [])]
    if watts:
        n = len(watts)
        np_ = normalized_power(watts) if n >= 30 else _avg(watts)
        avg = _avg(watts)
        zs = zone_seconds(watts, ftp)
        efforts = detect_efforts(watts, ftp)
        third = n // 3
        out.update(
            avg_power=round(avg), np=round(np_), intensity=round(np_ / ftp, 2) if ftp else None,
            vi=round(np_ / avg, 2) if avg else None, zones_s=zs,
            mmp={str(d): round(v) for d, v in mean_max_power(watts, MMP_DURATIONS).items()},
            efforts=efforts[:25], effort_count=len(efforts),
            time_above_ftp_s=sum(1 for w in watts if w > ftp),
            coasting_pct=round(sum(1 for w in watts if w < 10) / n * 100),
            matches=sum(1 for e in detect_efforts(watts, ftp, min_s=10, pct=1.2)),
        )
        if third >= 300:  # Pacing nur bei Fahrten ueber 15 min
            first, last = _avg(watts[:third]), _avg(watts[-third:])
            out["pacing"] = {"first_third_w": round(first), "last_third_w": round(last),
                             "change_pct": round((last - first) / first * 100) if first else None}
    if hr and any(hr):
        valid = [h for h in hr if h > 0]
        out["hr"] = {"avg": round(_avg(valid)), "max": round(max(valid))}
        if watts and len(watts) >= 2400 and len(hr) >= 2400:
            half = min(len(watts), len(hr)) // 2
            # Pw:HR-Entkopplung: Verhaeltnis Leistung/Puls erste gegen zweite Haelfte (nur rollende Abschnitte)
            def ratio(a: int, b: int) -> float | None:
                pairs = [(w, h) for w, h in zip(watts[a:b], hr[a:b]) if w >= 10 and h > 0]
                if len(pairs) < 600:
                    return None
                return _avg([p[0] for p in pairs]) / _avg([p[1] for p in pairs])
            r1, r2 = ratio(0, half), ratio(half, 2 * half)
            if r1 and r2:
                out["decoupling_pct"] = round((r1 - r2) / r1 * 100, 1)
            moving_hr = _avg([h for w, h in zip(watts, hr) if w >= 10 and h > 0])
            if moving_hr:
                out["ef"] = round((out.get("np") or 0) / moving_hr, 2)  # Efficiency Factor: NP / Puls
    if cadence and any(cadence):
        pedal = [c for c in cadence if c and c > 0]
        if pedal:
            out["cadence_avg"] = round(_avg(pedal))
    if duration_s:
        out["duration_s"] = duration_s
    return out


def plan_compliance(structure: list | None, ftp: float, watts: Sequence[float] | None, *,
                    planned_tss: float | None = None, actual_tss: float | None = None,
                    planned_duration_s: int | None = None, actual_duration_s: int | None = None) -> dict | None:
    """Soll/Ist eines geplanten Trainings. Mit Struktur und Leistungsdaten auch je Intervall (Plan wird zeitlich ausgerichtet)."""
    if structure is None and planned_tss is None and planned_duration_s is None:
        return None
    out: dict = {}
    if planned_tss and actual_tss is not None:
        out["tss"] = {"planned": round(planned_tss), "actual": round(actual_tss), "pct": round(actual_tss / planned_tss * 100)}
    if planned_duration_s and actual_duration_s:
        out["duration"] = {"planned_min": round(planned_duration_s / 60), "actual_min": round(actual_duration_s / 60),
                           "pct": round(actual_duration_s / planned_duration_s * 100)}
    if not structure or not watts or ftp <= 0:
        return out or None
    try:
        steps = [Repeat(**s) if s.get("type") == "repeat" else Leaf(**s) for s in structure]
    except (TypeError, ValueError):
        return out or None
    leaves = flatten(steps)
    plan: list[float] = []
    work: list[tuple[int, int, float, str]] = []  # (start, dauer, Ziel-Watt, Typ)
    for leaf in leaves:
        lo, hi = leaf.power_pct
        target = ftp * (lo + hi) / 200
        if leaf.type in ("interval", "steady") and (lo + hi) / 2 >= 76:
            work.append((len(plan), leaf.duration_s, target, leaf.type))
        plan.extend([target] * leaf.duration_s)
    if not work:
        return out or None
    w = [float(x or 0) for x in watts]
    prefix = [0.0]
    for x in w:
        prefix.append(prefix[-1] + x)

    def seg_avg(a: int, b: int) -> float | None:
        b = min(b, len(w))
        return (prefix[b] - prefix[a]) / (b - a) if b > a else None

    # Versatz bis 30 min, auch wenn die Fahrt kuerzer als der Plan ist (z. B. kuerzer ausgefahren)
    max_shift = max(0, min(1800, len(w) - work[0][1]))
    best, best_err = 0, float("inf")
    # Ausrichtung: Versatz, bei dem die Belastungsabschnitte am besten passen (grob in 5-s-Schritten, dann fein).
    # Nicht gefahrene Abschnitte zaehlen wie 0 W, damit ein Versatz Intervalle nicht einfach "aus der Fahrt schiebt".
    def err(shift: int) -> float:
        total = 0.0
        for start, dur, target, _ in work:
            avg = seg_avg(shift + start, shift + start + dur)
            total += abs((avg if avg is not None else 0.0) - target) * dur
        return total
    for shift in range(0, max_shift + 1, 5):
        e = err(shift)
        if e < best_err:
            best, best_err = shift, e
    for shift in range(max(0, best - 4), min(max_shift, best + 4) + 1):
        e = err(shift)
        if e < best_err:
            best, best_err = shift, e
    intervals = []
    for i, (start, dur, target, kind) in enumerate(work, 1):
        actual = seg_avg(best + start, best + start + dur) or 0.0
        pct = actual / target * 100 if target else 0
        status = "ok" if 95 <= pct <= 105 else "under" if pct < 95 else "over"
        intervals.append({"n": i, "type": kind, "duration_s": dur, "target_w": round(target), "actual_w": round(actual),
                          "pct": round(pct), "status": status})
    ok = sum(1 for x in intervals if x["status"] == "ok")
    out.update(
        offset_s=best, intervals=intervals[:40], interval_count=len(intervals),
        hit=ok, under=sum(1 for x in intervals if x["status"] == "under"), over=sum(1 for x in intervals if x["status"] == "over"),
        avg_pct=round(_avg([x["pct"] for x in intervals])),
    )
    if len(intervals) >= 3:  # Leistungsabfall ueber die Serie: letztes Drittel gegen erstes
        k = max(1, len(intervals) // 3)
        first, last = _avg([x["pct"] for x in intervals[:k]]), _avg([x["pct"] for x in intervals[-k:]])
        out["fade_pct"] = round(last - first)
    return out


def personal_bests(mmp: dict, history: list[dict]) -> list[dict]:
    """Bestwerte dieser Fahrt gegenueber den 90 Tagen davor. history: [{"mmp": {...}}]."""
    out = []
    for key, value in (mmp or {}).items():
        prev = max((h["mmp"].get(key, 0) for h in history if h.get("mmp")), default=0)
        if value and value > prev and prev > 0:
            out.append({"duration": MMP_LABELS.get(int(key), key), "watts": value, "previous": prev,
                        "gain_pct": round((value - prev) / prev * 100, 1)})
    return out


# ------------------------------------------------------- Belastung ---


def _flag(code: str, level: str, text: str, kind: str) -> dict:
    return {"code": code, "level": level, "text": text, "kind": kind}


def load_assessment(rows: list[dict], *, today: dt.date, planned_14d: float = 0.0, actual_14d: float = 0.0,
                    atp_last_week: dict | None = None, atp_phase_now: str | None = None,
                    event_within_days: int | None = None, ef_trend_pct: float | None = None) -> dict:
    """Ist die Belastung zu hoch, passend oder zu gering? rows: PMC bis heute (date, tss, ctl, atl, tsb).

    kind der Hinweise: too_much | too_little | info. Das Urteil ergibt sich aus den Warnungen.
    """
    flags: list[dict] = []
    days = len(rows)
    if days < 21:
        return {"verdict": "unknown", "flags": [_flag("few_data", "info", "Weniger als drei Wochen Daten: noch keine verlaessliche Einordnung.", "info")],
                "metrics": {}}
    last = rows[-1]
    ctl, atl = last["ctl"], last["atl"]
    tsb = ctl - atl
    ramp = ctl - rows[-8]["ctl"]
    ctl_21 = ctl - rows[-22]["ctl"]
    tsbs = [r["ctl"] - r["atl"] for r in rows[-10:]]
    week = [r["tss"] for r in rows[-7:]]
    sd = stddev(week)
    monotony = _avg(week) / sd if sd > 0 else None
    metrics = {"ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1), "ramp_7d": round(ramp, 1),
               "ctl_change_21d": round(ctl_21, 1), "tss_7d": round(sum(week)),
               "monotony_7d": round(monotony, 2) if monotony else None,
               "acute_chronic": round(atl / ctl, 2) if ctl >= 1 else None}
    taper_or_rest = atp_phase_now in ("peak", "race", "transition") or (event_within_days is not None and event_within_days <= 10)

    # zu viel
    if ramp > 8:
        flags.append(_flag("ramp_high", "alert", f"Fitness (CTL) steigt um {ramp:.1f} pro Woche, mehr als die Praxisregel von etwa 5-8.", "too_much"))
    elif ramp > 6:
        flags.append(_flag("ramp_ambitious", "info", f"CTL-Anstieg {ramp:.1f} pro Woche: ambitioniert, fuer Leistungssportler noch vertretbar.", "info"))
    if tsb < -30:
        flags.append(_flag("tsb_low", "alert", f"Form (TSB) {tsb:.0f}: sehr hohe Ermuedung, Ueberlastungsrisiko.", "too_much"))
    elif sum(1 for t in tsbs if t < -20) >= 7:
        flags.append(_flag("tsb_long_low", "warn", "Die Form liegt seit ueber einer Woche unter -20: Erholung einplanen.", "too_much"))
    if ctl >= 20 and atl / ctl > 1.5:
        flags.append(_flag("spike", "warn", f"Kurzfristige Last (ATL {atl:.0f}) ist mehr als 1,5-mal so hoch wie die Fitness (CTL {ctl:.0f}): Lastspitze.", "too_much"))
    if monotony and monotony > 2.0 and sum(week) > 350:
        flags.append(_flag("monotony", "warn", f"Monotonie {monotony:.1f} (Foster): wenig Wechsel zwischen harten und leichten Tagen.", "too_much"))
    if planned_14d >= 150 and actual_14d > planned_14d * 1.25:
        flags.append(_flag("over_plan", "warn", f"Letzte 14 Tage {actual_14d:.0f} TSS statt geplant {planned_14d:.0f}: deutlich mehr als vorgesehen.", "too_much"))
    if ef_trend_pct is not None and ef_trend_pct <= -5:
        flags.append(_flag("ef_drop", "warn", f"Bei Grundlagenfahrten ist der Puls bei gleicher Leistung hoeher als zuvor (Efficiency Factor {ef_trend_pct:+.0f} %): moegliches Zeichen von Ermuedung, Hitze oder Krankheit.", "too_much"))

    # zu wenig
    if planned_14d >= 150 and actual_14d < planned_14d * 0.7:
        flags.append(_flag("under_plan", "warn", f"Letzte 14 Tage {actual_14d:.0f} TSS statt geplant {planned_14d:.0f}: Plan zu ambitioniert oder Einheiten verpasst.", "too_little"))
    if atp_last_week and atp_last_week.get("target", 0) > 0 and not atp_last_week.get("recovery"):
        ratio = atp_last_week["actual"] / atp_last_week["target"]
        if ratio < 0.8:
            flags.append(_flag("under_atp", "warn", f"Letzte Woche {atp_last_week['actual']:.0f} TSS bei einem Wochenziel von {atp_last_week['target']:.0f}.", "too_little"))
        elif ratio > 1.2:
            flags.append(_flag("over_atp", "warn", f"Letzte Woche {atp_last_week['actual']:.0f} TSS bei einem Wochenziel von {atp_last_week['target']:.0f}.", "too_much"))
    if not taper_or_rest:
        if ctl_21 < -5:
            flags.append(_flag("ctl_falling", "warn", f"Die Fitness sinkt seit drei Wochen ({ctl_21:+.0f} CTL).", "too_little"))
        if sum(1 for t in tsbs if t > 15) >= 7:
            flags.append(_flag("tsb_long_high", "warn", "Die Form liegt seit ueber einer Woche ueber +15, ohne dass ein Event ansteht: zu wenig Trainingsreiz.", "too_little"))
    elif atp_phase_now == "transition" and ctl_21 < -5:
        flags.append(_flag("transition", "info", "Die Fitness sinkt, das passt zur Uebergangsphase im Saisonplan.", "info"))
    if ef_trend_pct is not None and ef_trend_pct >= 5:
        flags.append(_flag("ef_rise", "info", f"Efficiency Factor {ef_trend_pct:+.0f} %: mehr Leistung bei gleichem Puls, die Grundlage verbessert sich.", "info"))

    much = [f for f in flags if f["kind"] == "too_much"]
    little = [f for f in flags if f["kind"] == "too_little"]
    if any(f["level"] == "alert" for f in much) or len(much) >= 2:
        verdict = "too_much"
    elif much and not little:
        verdict = "slightly_much"
    elif little and not much:
        verdict = "too_little"
    elif much and little:
        verdict = "mixed"
    else:
        verdict = "ok"
    return {"verdict": verdict, "flags": flags, "metrics": metrics}


def ef_trend(rides: list[dict], today: dt.date) -> float | None:
    """Veraenderung des Efficiency Factor bei Grundlagenfahrten: letzte 14 Tage gegen die 42 Tage davor (in %)."""
    recent = [r["ef"] for r in rides if r.get("ef") and (today - r["date"]).days < 14]
    before = [r["ef"] for r in rides if r.get("ef") and 14 <= (today - r["date"]).days < 56]
    if len(recent) < 2 or len(before) < 3:
        return None
    b = _avg(before)
    return round((_avg(recent) - b) / b * 100, 1) if b else None


# ------------------------------------------------------------- FTP ---


def critical_power(mmp: dict[int, float]) -> dict | None:
    """CP und W' aus Bestleistungen zwischen 3 und 20 min (lineares Arbeit-Zeit-Modell). Braucht mindestens 3 Dauern."""
    pts = [(d, p) for d, p in mmp.items() if 180 <= d <= 1200 and p > 0]
    if len(pts) < 3 or max(d for d, _ in pts) < 600:
        return None
    xs = [d for d, _ in pts]
    ys = [d * p for d, p in pts]
    mx, my = _avg(xs), _avg(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    cp = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    w_prime = my - cp * mx
    if cp <= 0 or w_prime <= 0:
        return None
    return {"cp": round(cp), "w_prime_kj": round(w_prime / 1000, 1)}


def _median(xs: list[float]) -> float:
    ys = sorted(xs)
    n = len(ys)
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2


def ftp_assessment(ftp: float, rides: list[dict], today: dt.date, ctl_by_date: dict[dt.date, float] | None = None) -> dict:
    """Passt die eingestellte FTP? rides: [{date, name, duration_s, np, mmp: {sek: watt} | None}] der letzten 90 Tage.

    Schaetzer (Praxisregeln): 95 % der besten 20 min, 97 % der besten 30 min, beste 60 min, NP der haertesten langen Fahrt,
    95 % der Critical Power aus 3-20 min. Die Schaetzung ist der Median der Schaetzer aus den letzten 6 Wochen, damit ein
    einzelner Wert (z. B. ein starker 20-min-Anstieg) die FTP nicht ueberschaetzt.
    Empfehlung: raise (anheben), hold (Werte lagen hoeher, die Fitness ist seitdem deutlich gesunken), ok, test (unbestaetigt).
    """
    def bests(max_age: int) -> dict[int, tuple[float, dt.date, str]]:
        out: dict[int, tuple[float, dt.date, str]] = {}
        for r in rides:
            if (today - r["date"]).days > max_age:
                continue
            for k, v in (r.get("mmp") or {}).items():
                d = int(k)
                if v and (d not in out or v > out[d][0]):
                    out[d] = (float(v), r["date"], r.get("name") or "Fahrt")
        return out

    def candidates(max_age: int) -> list[dict]:
        found: list[dict] = []
        b = bests(max_age)
        for d, factor, label in ((1200, 0.95, "95 % der besten 20 min"), (1800, 0.97, "97 % der besten 30 min"), (3600, 1.0, "beste 60 min")):
            if d in b:
                v, day, name = b[d]
                found.append({"source": f"mmp_{d}", "date": day.isoformat(), "name": name, "estimate": round(v * factor),
                              "detail": f"{label}: {v:.0f} W", "age_days": (today - day).days})
        # Haerteste lange Fahrt (NP): auch ohne Sensordaten aussagekraeftig
        long = [r for r in rides if (today - r["date"]).days <= max_age and (r.get("duration_s") or 0) >= 2400 and r.get("np")]
        if long:
            r = max(long, key=lambda x: x["np"] * (1.0 if x["duration_s"] >= 3600 else 0.97))
            est = r["np"] * (1.0 if r["duration_s"] >= 3600 else 0.97)
            found.append({"source": "np_long_ride", "date": r["date"].isoformat(), "name": r.get("name"), "estimate": round(est),
                          "detail": f"NP {r['np']:.0f} W ueber {r['duration_s'] // 60} min", "age_days": (today - r["date"]).days})
        # Nur annaehernd maximale Belastungen zaehlen: laengere Bestwerte, die weit unter den 20 min liegen, waren locker gefahren
        ref = b[1200][0] if 1200 in b else None
        if ref:
            share = {"mmp_1800": 0.9, "mmp_3600": 0.85, "np_long_ride": 0.9}
            found = [e for e in found if e["source"] not in share
                     or e["estimate"] / (0.97 if e["source"] == "mmp_1800" else 1.0) >= ref * share[e["source"]]]
        cp = critical_power({d: v[0] for d, v in b.items()})
        if cp:
            found.append({"source": "cp", "date": None, "name": None, "estimate": round(cp["cp"] * 0.95),
                          "detail": f"95 % der Critical Power ({cp['cp']} W aus Bestwerten 3-20 min)", "age_days": None})
        return found

    best90 = bests(90)
    out: dict = {"ftp": round(ftp), "best_efforts": {MMP_LABELS[d]: {"watts": round(v[0]), "date": v[1].isoformat()}
                                                    for d, v in sorted(best90.items()) if d in MMP_LABELS}}
    cp90 = critical_power({d: v[0] for d, v in best90.items()})
    if cp90:
        out["critical_power"] = cp90
    recent = candidates(42)
    older = [e for e in candidates(90) if e["source"] != "cp" and (e["age_days"] or 0) > 42]
    out["evidence"] = sorted(recent, key=lambda e: -e["estimate"]) + older[:2]
    strong = [e for e in recent if e["source"] in ("mmp_1200", "mmp_1800", "mmp_3600", "np_long_ride")]
    if not strong:
        out.update(recommendation="test", confidence="low",
                   reason="In den letzten 6 Wochen gab es keine langen, harten Belastungen; die FTP ist nicht bestaetigt. "
                          "Ein FTP-Test oder ein Rennen wuerde sie pruefen.")
        return out
    ests = [e["estimate"] for e in recent]
    estimate = round(_median(ests))
    spread = (max(ests) - min(ests)) / estimate if estimate else 1
    out["estimate"] = estimate
    if max(e["estimate"] for e in strong) < ftp * 0.92:
        out.update(recommendation="test", confidence="low",
                   reason=f"Die haertesten Belastungen der letzten 6 Wochen ergeben nur etwa {estimate} W; das kann an fehlenden "
                          "Maximalbelastungen liegen. Ein FTP-Test zeigt, ob die eingestellte FTP noch stimmt.")
        return out
    if estimate >= ftp * 1.03 and estimate - ftp >= 5:
        newest = max(strong, key=lambda e: e["date"])
        day = dt.date.fromisoformat(newest["date"])
        ctl_then, ctl_now = (ctl_by_date or {}).get(day), (ctl_by_date or {}).get(today)
        if ctl_then and ctl_now and ctl_now < ctl_then * 0.9:
            out.update(recommendation="hold", confidence="medium",
                       reason=f"Die Belastungen bis {newest['date']} ergeben etwa {estimate} W, mehr als die eingestellten {ftp:.0f} W. "
                              f"Seitdem ist die Fitness (CTL) aber um {round((1 - ctl_now / ctl_then) * 100)} % gesunken; "
                              "die FTP besser nach dem Wiedereinstieg mit einem Test pruefen, statt sie jetzt anzuheben.")
            return out
        top3 = ", ".join(e["detail"] for e in sorted(recent, key=lambda e: -e["estimate"])[:3])
        out.update(recommendation="raise", suggested_ftp=int(round(estimate / 5) * 5),
                   confidence="high" if len(ests) >= 2 and spread <= 0.08 and estimate >= ftp * 1.05 else "medium",
                   reason=f"Die Belastungen der letzten 6 Wochen ergeben im Mittel etwa {estimate} W ({top3}), "
                          f"mehr als die eingestellten {ftp:.0f} W.")
        return out
    out.update(recommendation="ok", confidence="medium" if len(ests) >= 2 else "low",
               reason=f"Die harten Belastungen der letzten Wochen ergeben etwa {estimate} W und passen zur eingestellten FTP.")
    return out
