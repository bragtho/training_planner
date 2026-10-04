from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..metrics.power import power_zones
from ..models import AthleteProfile, User
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


def _out(p: AthleteProfile) -> ProfileOut:
    return ProfileOut(
        name=p.name, ftp=p.ftp, hr_max=p.hr_max, hr_rest=p.hr_rest, lthr=p.lthr,
        weight_kg=p.weight_kg, goals=p.goals, availability=p.availability, zones=power_zones(p.ftp),
    )


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(current_user)):
    return _out(user.profile)


@router.put("", response_model=ProfileOut)
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.merge(user.profile)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return _out(p)
