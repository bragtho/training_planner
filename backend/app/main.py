from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers import activities, atp, auth, coach, insights, knowledge, plans, profile, strava

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Fuer Dev; spaeter durch Alembic-Migrationen ersetzen
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Training Planner API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)  # Entwicklung; in Produktion auf die App-Origin einschraenken

app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(strava.router)
app.include_router(activities.router)
app.include_router(plans.router)
app.include_router(coach.router)
app.include_router(atp.router)
app.include_router(knowledge.router)
app.include_router(insights.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
