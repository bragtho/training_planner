from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import Base, engine
from .routers import auth, profile

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
