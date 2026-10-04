import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def setup_module():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_register_login_profile():
    c = TestClient(app)
    r = c.post("/auth/register", json={"email": "a@b.de", "password": "geheim123"})
    assert r.status_code == 200
    assert c.post("/auth/register", json={"email": "a@b.de", "password": "geheim123"}).status_code == 409
    assert c.post("/auth/login", json={"email": "a@b.de", "password": "falsch"}).status_code == 401
    token = c.post("/auth/login", json={"email": "a@b.de", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert c.get("/profile").status_code == 401
    r = c.put("/profile", json={"ftp": 250}, headers=h)
    assert r.status_code == 200 and r.json()["zones"][3]["max"] == 262
