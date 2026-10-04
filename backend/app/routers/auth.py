from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AthleteProfile, User
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str


@router.post("/register", response_model=TokenOut)
def register(body: Credentials, db: Session = Depends(get_db)):
    if len(body.password) < 8:
        raise HTTPException(422, "Passwort muss mindestens 8 Zeichen haben")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "E-Mail bereits registriert")
    user = User(email=body.email, password_hash=hash_password(body.password))
    user.profile = AthleteProfile()
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    return TokenOut(access_token=create_token(user.id))
