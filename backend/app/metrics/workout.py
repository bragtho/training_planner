"""Struktur geplanter Workouts (Intervallbloecke in % FTP) und daraus abgeleitete Kennzahlen.

Format (identisch fuer App, Coach und spaetere Wahoo/FIT-Exporte):
    leaf:   {"type": "warmup|steady|interval|rest|cooldown", "duration_s": 600, "power_pct": [50, 70]}
    repeat: {"type": "repeat", "count": 4, "steps": [leaf, leaf, ...]}   # nicht verschachtelbar
`power_pct` ist [von, bis] in % der FTP. Aufwaermen/Ausfahren werden als Rampe von->bis gefahren,
alle anderen Schritte konstant mit dem Mittelwert.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator
from pydantic.functional_validators import AfterValidator

from .power import intensity_factor, normalized_power, tss

MAX_TOTAL_S = 12 * 3600
RAMP_TYPES = {"warmup", "cooldown"}


class Leaf(BaseModel):
    type: Literal["warmup", "steady", "interval", "rest", "cooldown"]
    duration_s: int = Field(ge=5, le=MAX_TOTAL_S)
    power_pct: list[float] = Field(min_length=2, max_length=2)

    @field_validator("power_pct")
    @classmethod
    def _range(cls, v: list[float]) -> list[float]:
        if any(p < 20 or p > 250 for p in v):
            raise ValueError("Leistung muss zwischen 20 und 250 % FTP liegen")
        return v


class Repeat(BaseModel):
    type: Literal["repeat"]
    count: int = Field(ge=1, le=50)
    steps: list[Leaf] = Field(min_length=1, max_length=10)


def _total_ok(steps: list) -> list:
    if total_duration(steps) > MAX_TOTAL_S:
        raise ValueError("Workout darf hoechstens 12 Stunden dauern")
    return steps


Step = Annotated[Union[Leaf, Repeat], Field(discriminator="type")]
Steps = Annotated[list[Step], Field(min_length=1, max_length=60), AfterValidator(_total_ok)]


def flatten(steps: list[Leaf | Repeat]) -> list[Leaf]:
    out: list[Leaf] = []
    for s in steps:
        if isinstance(s, Repeat):
            out.extend(s.steps * s.count)
        else:
            out.append(s)
    return out


def total_duration(steps: list[Leaf | Repeat]) -> int:
    return sum(
        sum(x.duration_s for x in s.steps) * s.count if isinstance(s, Repeat) else s.duration_s
        for s in steps
    )


def power_series(steps: list[Leaf | Repeat], ftp: float) -> list[float]:
    """Synthetische 1-Hz-Leistungsreihe in Watt."""
    out: list[float] = []
    for leaf in flatten(steps):
        lo, hi = leaf.power_pct
        n = leaf.duration_s
        if leaf.type in RAMP_TYPES and n > 1:
            out.extend(ftp * (lo + (hi - lo) * i / (n - 1)) / 100 for i in range(n))
        else:
            out.extend([ftp * (lo + hi) / 2 / 100] * n)
    return out


def summarize(steps: list[Leaf | Repeat], ftp: float) -> dict:
    watts = power_series(steps, ftp)
    dur = len(watts)
    np_ = normalized_power(watts) if dur >= 30 else (sum(watts) / dur if dur else 0.0)
    return {
        "duration_s": dur,
        "np": round(np_, 1),
        "intensity_factor": round(intensity_factor(np_, ftp), 2),
        "tss": round(tss(dur, np_, ftp), 1),
    }
