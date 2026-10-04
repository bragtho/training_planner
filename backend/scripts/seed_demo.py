"""Erzeugt einen Demo-Nutzer mit ~4 Monaten Fahrten, um die App ohne Strava auszuprobieren.

Aufruf (eigene Datenbank, damit echte Daten unberuehrt bleiben):
    DATABASE_URL=sqlite:///./demo.db python scripts/seed_demo.py
    DATABASE_URL=sqlite:///./demo.db uvicorn app.main:app --port 8001
Login: demo@example.com / demo12345
"""

import math
import random
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.metrics.power import intensity_factor, tss  # noqa: E402
from app.models import Activity, AthleteProfile, User  # noqa: E402
from app.security import hash_password  # noqa: E402

FTP = 260.0


def main() -> None:
    Base.metadata.create_all(engine)
    rnd = random.Random(7)
    with SessionLocal() as db:
        if db.query(User).filter_by(email="demo@example.com").first():
            print("Demo-Nutzer existiert bereits.")
            return
        u = User(email="demo@example.com", password_hash=hash_password("demo12345"))
        u.profile = AthleteProfile(name="Demo", ftp=FTP, hr_max=188, hr_rest=48, lthr=168, weight_kg=72)
        db.add(u)
        db.flush()
        today = datetime.now().date()
        n = 0
        for back in range(120, 0, -1):
            day = today - timedelta(days=back)
            week = (120 - back) // 7
            plan = {1: 0.0, 3: 0.8, 5: 1.0, 6: 1.6}  # Wochentag -> Umfang
            vol = plan.get(day.weekday())
            if vol is None or rnd.random() < 0.1:
                continue
            ramp = 1 + 0.03 * (week % 4 != 3) * week * 0.3 - (0.35 if week % 4 == 3 else 0)
            dur = int(3600 * vol * ramp * rnd.uniform(0.85, 1.15)) or 2400
            np_ = FTP * rnd.uniform(0.62, 0.86) * (1.08 if day.weekday() == 3 else 1)
            n += 1
            db.add(Activity(
                user_id=u.id, source="strava", external_id=f"demo{n}",
                name=["Grundlagenrunde", "Intervalle", "Lange Ausfahrt", "Sweetspot"][n % 4],
                sport="Ride", start_time=datetime.combine(day, time(8, 0), tzinfo=timezone.utc),
                duration_s=dur, distance_m=dur / 3600 * rnd.uniform(24000, 31000),
                elevation_m=dur / 3600 * rnd.uniform(150, 450), avg_power=np_ * 0.93, norm_power=np_,
                avg_hr=140 + 25 * (np_ / FTP - 0.6), intensity_factor=intensity_factor(np_, FTP),
                tss=tss(dur, np_, FTP), ftp_used=FTP,
                streams={
                    "time": list(range(0, dur, 10)),
                    "watts": [max(0, round(np_ * 0.93 + 60 * math.sin(i / 25) + rnd.uniform(-25, 25))) for i in range(0, dur, 10)],
                    "heartrate": [round(120 + 40 * (np_ / FTP - 0.5) + 6 * math.sin(i / 40)) for i in range(0, dur, 10)],
                    "altitude": [round(300 + 80 * math.sin(i / 90)) for i in range(0, dur, 10)],
                },
            ))
        db.commit()
        print(f"{n} Demo-Fahrten angelegt.")


if __name__ == "__main__":
    main()
