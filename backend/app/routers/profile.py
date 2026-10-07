from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import insights as I
from ..db import get_db
from ..metrics.power import power_zones
from ..models import AthleteProfile, FtpChange, User
from sqlalchemy import select
from ..security import current_user

router = APIRouter(prefix="/profile", tags=["profile"])


class ProfileIn(BaseModel):
    name: str | None = None
    ftp: float | None = Field(None, gt=50, lt=700)
    hr_max: int | None = Field(None, gt=100, lt=230)
    hr_rest: int | None = Field(None, gt=25, lt=120)
    lthr: int | None = Field(None, gt=100, lt=220)
    weight_kg: float | None = Field(None, gt=30, lt=200)
    goals: str | None = None
    availability: dict[str, int] | None = None


class ProfileOut(ProfileIn):
    ftp: float
    zones: list[dict]
    ftp_change: dict | None = None  # letzte automatische Aenderung durch den Coach (30 Tage), mit Rueckgaengig


def _out(p: AthleteProfile, change: dict | None = None) -> ProfileOut:
    return ProfileOut(
        name=p.name, ftp=p.ftp, hr_max=p.hr_max, hr_rest=p.hr_rest, lthr=p.lthr,
        weight_kg=p.weight_kg, goals=p.goals, availability=p.availability, zones=power_zones(p.ftp), ftp_change=change,
    )


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(user.profile, I.ftp_change_view(db, user.id))


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.merge(user.profile)
    data = body.model_dump(exclude_unset=True)
    new_ftp = data.pop("ftp", None)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    if new_ftp is not None:
        # Manuelle Aenderung wird festgehalten; sie pausiert automatische Anhebungen fuer 28 Tage
        I.set_ftp(db, user, new_ftp, source="user", reason="Manuell im Profil geaendert")
        p = user.profile
    return _out(p, I.ftp_change_view(db, user.id))


@router.get("/ftp-history")
def ftp_history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Die letzten FTP-Aenderungen (automatisch, manuell, rueckgaengig)."""
    rows = db.scalars(select(FtpChange).where(FtpChange.user_id == user.id).order_by(FtpChange.id.desc()).limit(10))
    return [{"date": r.changed_at.date().isoformat(), "old_ftp": r.old_ftp, "new_ftp": r.new_ftp, "source": r.source,
             "reason": r.reason} for r in rows]


@router.post("/ftp/undo", response_model=ProfileOut)
def undo_ftp(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Macht die letzte automatische FTP-Anhebung des Coaches rueckgaengig; automatische Anhebungen ruhen danach 28 Tage."""
    try:
        I.undo_ftp(db, user)
    except I.InsightError as e:
        raise HTTPException(e.status, str(e))
    return _out(user.profile, I.ftp_change_view(db, user.id))
