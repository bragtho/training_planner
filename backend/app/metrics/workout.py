"""Struktur geplanter Workouts (Intervallbloecke in % FTP) und daraus abgeleitete Kennzahlen.

Format (identisch fuer App, Coach und spaetere Wahoo/FIT-Exporte):
    leaf:   {"type": "warmup|steady|interval|rest|cooldown", "duration_s": 600, "power_pct": [50, 70]}
    repeat: {"type": "repeat", "count": 4, "steps": [leaf, leaf, ...]}   # nicht verschachtelbar
    exercise (Krafttraining): {"type": "exercise", "exercise_id": "squat", "name": "Kniebeuge", "sets": 3, "reps": 10, "rest_s": 90, "load": "Kurzhanteln 16 kg"}
        statt `reps` geht `duration_s` (Haltezeit je Satz, z. B. Plank). Ein Krafttraining besteht nur aus exercise-Schritten.
`power_pct` ist [von, bis] in % der FTP. Aufwaermen/Ausfahren werden als Rampe von->bis gefahren,
alle anderen Schritte konstant mit dem Mittelwert.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.functional_validators import AfterValidator

from ..exercises import EXERCISES, match_id
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


class Exercise(BaseModel):
    """Eine Kraftuebung mit Saetzen; entweder Wiederholungen oder eine Haltezeit je Satz."""

    type: Literal["exercise"]
    exercise_id: str | None = None  # Kennung aus app/exercises.py (Anleitung und Bild in der App)
    name: str = Field(min_length=1, max_length=80)
    sets: int = Field(ge=1, le=10)
    reps: int | None = Field(None, ge=1, le=100)
    duration_s: int | None = Field(None, ge=5, le=600)  # Haltezeit je Satz
    rest_s: int = Field(60, ge=0, le=600)  # Pause zwischen den Saetzen
    load: str | None = Field(None, max_length=80)  # z. B. "Koerpergewicht", "Kurzhanteln 16 kg", "RPE 7"
    note: str | None = Field(None, max_length=200)

    @model_validator(mode="before")
    @classmethod
    def _name_from_catalog(cls, data):
        if not isinstance(data, dict):
            return data
        if data.get("exercise_id") and not data.get("name"):
            entry = EXERCISES.get(data["exercise_id"])
            if entry:
                data = {**data, "name": entry["name"]}
        elif not data.get("exercise_id") and match_id(data.get("name")):
            data = {**data, "exercise_id": match_id(data.get("name"))}  # frei benannte Uebung dem Katalog zuordnen
        return data

    @field_validator("exercise_id")
    @classmethod
    def _known_id(cls, v: str | None) -> str | None:
        if v is not None and v not in EXERCISES:
            raise ValueError(f"Unbekannte Uebung '{v}'. Erlaubt: {', '.join(EXERCISES)}")
        return v

    @model_validator(mode="after")
    def _reps_or_hold(self) -> "Exercise":
        if (self.reps is None) == (self.duration_s is None):
            raise ValueError("Entweder reps (Wiederholungen) oder duration_s (Haltezeit) angeben, nicht beides")
        return self


REP_SECONDS = 3  # Annahme: 3 s je Wiederholung (kontrolliertes Tempo)
TRANSITION_S = 45  # Wechsel zur naechsten Uebung


def exercise_duration(e: Exercise) -> int:
    work = e.duration_s if e.duration_s is not None else (e.reps or 0) * REP_SECONDS
    return e.sets * work + (e.sets - 1) * e.rest_s + TRANSITION_S


def is_strength(structure: list | None) -> bool:
    """Ist die gespeicherte Struktur ein Krafttraining (nur exercise-Schritte)?"""
    return bool(structure) and all(isinstance(s, dict) and s.get("type") == "exercise" for s in structure)


class Repeat(BaseModel):
    type: Literal["repeat"]
    count: int = Field(ge=1, le=50)
    steps: list[Leaf] = Field(min_length=1, max_length=10)


def _total_ok(steps: list) -> list:
    strength = [isinstance(s, Exercise) for s in steps]
    if any(strength) and not all(strength):
        raise ValueError("Krafttraining (exercise) und Radschritte lassen sich nicht in einem Training mischen")
    if total_duration(steps) > MAX_TOTAL_S:
        raise ValueError("Workout darf hoechstens 12 Stunden dauern")
    return steps


Step = Annotated[Union[Leaf, Repeat, Exercise], Field(discriminator="type")]
Steps = Annotated[list[Step], Field(min_length=1, max_length=60), AfterValidator(_total_ok)]


def flatten(steps: list[Leaf | Repeat | Exercise]) -> list[Leaf]:
    out: list[Leaf] = []
    for s in steps:
        if isinstance(s, Repeat):
            out.extend(s.steps * s.count)
        elif isinstance(s, Leaf):
            out.append(s)
    return out


def total_duration(steps: list[Leaf | Repeat | Exercise]) -> int:
    return sum(
        exercise_duration(s) if isinstance(s, Exercise)
        else sum(x.duration_s for x in s.steps) * s.count if isinstance(s, Repeat) else s.duration_s
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


def summarize(steps: list[Leaf | Repeat | Exercise], ftp: float) -> dict:
    if steps and all(isinstance(s, Exercise) for s in steps):
        # Krafttraining: Dauer, aber keine TSS (ohne Leistungsmesser nicht vergleichbar mit Radtraining)
        return {"kind": "strength", "duration_s": total_duration(steps), "np": 0.0, "intensity_factor": 0.0, "tss": None}
    watts = power_series(steps, ftp)
    dur = len(watts)
    np_ = normalized_power(watts) if dur >= 30 else (sum(watts) / dur if dur else 0.0)
    return {
        "duration_s": dur,
        "np": round(np_, 1),
        "intensity_factor": round(intensity_factor(np_, ftp), 2),
        "tss": round(tss(dur, np_, ftp), 1),
    }
