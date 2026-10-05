"""Alle Tabellen tragen user_id -> Umbau auf Mehrbenutzerbetrieb ohne Schemaaenderung."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class ActivityInsight(Base):
    """Analyse einer Aktivitaet: Kennzahlen aus den Sensordaten und das Feedback des Coaches (eigene Tabelle,
    weil sich Spalten an bestehenden Tabellen ohne Migration nicht ergaenzen lassen)."""

    __tablename__ = "activity_insights"
    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    workout_type: Mapped[int | None] = mapped_column(Integer)  # Strava: 11 = Rennen, 12 = Workout
    metrics: Mapped[dict | None] = mapped_column(JSON)  # siehe app/metrics/analysis.py (ride_metrics)
    feedback: Mapped[dict | None] = mapped_column(JSON)  # Feedback des Coaches (headline, summary, ...)
    feedback_status: Mapped[str] = mapped_column(String(10), default="none")  # none | done | failed
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


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


class AtpWeek(Base):
    """Eine Woche im Saisonplan (ATP, Annual Training Plan): Phase und Wochenziel."""

    __tablename__ = "atp_weeks"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)  # immer ein Montag
    phase: Mapped[str] = mapped_column(String(20))  # preparation|base|build|peak|race|transition
    tss_target: Mapped[float] = mapped_column(Float)
    hours_target: Mapped[float | None] = mapped_column(Float)
    recovery: Mapped[bool] = mapped_column(Boolean, default=False)  # Entlastungswoche
    note: Mapped[str | None] = mapped_column(String(200))


class SeasonEvent(Base):
    """Wettkampf oder Ziel im Saisonplan mit Prioritaet A (Hauptziel), B oder C."""

    __tablename__ = "season_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(120))
    priority: Mapped[str] = mapped_column(String(1), default="B")
    notes: Mapped[str | None] = mapped_column(String(300))


class KnowledgeSource(Base):
    """Eine geprueft erfasste Studie oder ein Konsens-Statement, auf das sich Wissenskarten stuetzen."""

    __tablename__ = "knowledge_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    authors: Mapped[str] = mapped_column(String(300))
    year: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    journal: Mapped[str | None] = mapped_column(String(200))
    doi: Mapped[str | None] = mapped_column(String(120), index=True)
    pmid: Mapped[str | None] = mapped_column(String(20), index=True)
    design: Mapped[str] = mapped_column(String(30))
    sample_n: Mapped[int | None] = mapped_column(Integer)
    population: Mapped[str | None] = mapped_column(String(200))
    basis: Mapped[str] = mapped_column(String(10), default="abstract")  # fulltext | abstract
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    retraction_checked: Mapped[date | None] = mapped_column(Date)


class KnowledgeCard(Base):
    """Eine Wissenskarte: handlungsnahe Empfehlung mit Evidenzgrad, Gueltigkeitsbereich, Grenzen und belegten Aussagen."""

    __tablename__ = "knowledge_cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    topic: Mapped[str] = mapped_column(String(40), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(String(1))  # A | B | C | D
    directness: Mapped[str] = mapped_column(String(12))  # direct | indirect | extrapolated
    applies_to: Mapped[dict] = mapped_column(JSON, default=dict)
    caveats: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active | contested | watch | retired
    positions: Mapped[list | None] = mapped_column(JSON)  # bei contested: Lager mit Quellen
    safety: Mapped[bool] = mapped_column(Boolean, default=False)
    claims: Mapped[list] = mapped_column(JSON, default=list)  # [{text, quote, source_key}]
    reviewed: Mapped[date] = mapped_column(Date)
    review_due: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class KnowledgeHistory(Base):
    """Aenderungsverlauf einer Karte (jede Version als Momentaufnahme)."""

    __tablename__ = "knowledge_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_slug: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(12))  # created | updated | retired
    snapshot: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(String(300))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class KnowledgeCandidate(Base):
    """Vorschlag des Wissens-Managers aus einer Studie; erst nach Entscheidung des Nutzers wird daraus eine Karte."""

    __tablename__ = "knowledge_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    doi: Mapped[str | None] = mapped_column(String(120), index=True)
    pmid: Mapped[str | None] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(500))
    topic: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | accepted | rejected | watch
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)  # KI-Zusammenfassung, Zitat-Pruefung, Gegenpruefung, Rueckzugsstatus
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
