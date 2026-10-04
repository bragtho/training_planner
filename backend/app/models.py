"""Alle Tabellen tragen user_id -> Umbau auf Mehrbenutzerbetrieb ohne Schemaaenderung."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    profile: Mapped["AthleteProfile"] = relationship(back_populates="user", uselist=False)


class AthleteProfile(Base):
    __tablename__ = "athlete_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(100))
    ftp: Mapped[float] = mapped_column(Float, default=200.0)
    hr_max: Mapped[int | None] = mapped_column(Integer)
    hr_rest: Mapped[int | None] = mapped_column(Integer)
    lthr: Mapped[int | None] = mapped_column(Integer)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    goals: Mapped[str | None] = mapped_column(Text)
    # z. B. {"mon": 60, "tue": 90, ...} verfuegbare Minuten je Wochentag
    availability: Mapped[dict | None] = mapped_column(JSON)
    user: Mapped[User] = relationship(back_populates="profile")


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # strava | wahoo
    external_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[int] = mapped_column(Integer)  # Unix-Zeit
    sync_cursor: Mapped[int | None] = mapped_column(Integer)  # letzte importierte Aktivitaetszeit
    scope: Mapped[str | None] = mapped_column(String(255))


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))  # strava | fit_upload | wahoo
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(255))
    sport: Mapped[str] = mapped_column(String(30), default="Ride")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_s: Mapped[int] = mapped_column(Integer, default=0)
    distance_m: Mapped[float] = mapped_column(Float, default=0.0)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    avg_power: Mapped[float | None] = mapped_column(Float)
    norm_power: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    intensity_factor: Mapped[float | None] = mapped_column(Float)
    tss: Mapped[float | None] = mapped_column(Float)
    ftp_used: Mapped[float | None] = mapped_column(Float)
    streams: Mapped[dict | None] = mapped_column(JSON)  # {"watts": [...], "hr": [...], ...}
    planned_workout_id: Mapped[int | None] = mapped_column(ForeignKey("planned_workouts.id"))


class PlannedWorkout(Base):
    __tablename__ = "planned_workouts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # Format siehe app/metrics/workout.py (Schritte und Wiederholungsgruppen in % FTP)
    structure: Mapped[list | None] = mapped_column(JSON)
    planned_tss: Mapped[float | None] = mapped_column(Float)
    planned_duration_s: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned|completed|skipped
    created_by: Mapped[str] = mapped_column(String(10), default="user")  # user | coach
    wahoo_workout_id: Mapped[str | None] = mapped_column(String(64))


class CoachMessage(Base):
    __tablename__ = "coach_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[list | str] = mapped_column(JSON)  # Anthropic-Content-Bloecke
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class CoachMemory(Base):
    """Was der Coach sich langfristig ueber den Athleten merkt (Vorlieben, Saisonphase, Einschraenkungen ...)."""

    __tablename__ = "coach_memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(String(300))
    valid_until: Mapped[date | None] = mapped_column(Date)  # zeitlich begrenzte Fakten, z. B. Offseason
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
