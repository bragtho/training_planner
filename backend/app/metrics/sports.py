"""Sportarten (Strava sport_type): Zuordnung zu Radtraining, Laufen/Gehen und Krafttraining."""

from __future__ import annotations

CYCLING_HINT = "Ride"  # Ride, GravelRide, MountainBikeRide, EBikeRide, VirtualRide, Handcycle ...
RUN_LIKE = {"Run", "TrailRun", "VirtualRun", "Walk", "Hike", "Snowshoe"}
STRENGTH = {"WeightTraining", "Workout", "Crossfit", "HighIntensityIntervalTraining"}


def is_cycling(sport: str | None) -> bool:
    return CYCLING_HINT in (sport or "")


def is_run_like(sport: str | None) -> bool:
    return (sport or "") in RUN_LIKE


def is_strength(sport: str | None) -> bool:
    return (sport or "") in STRENGTH
