import datetime as dt
import json
from contextlib import contextmanager
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.coach import agent
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Activity, AthleteProfile, CoachMessage, PlannedWorkout, User

TOMORROW = (dt.date.today() + dt.timedelta(days=1)).isoformat()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


# ----------------------------------------------------------------- Fake-Client ---


def text(t):
    return NS(type="text", text=t)


def tool(id_, name, **inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def msg(*blocks, stop="end_turn"):
    return NS(stop_reason=stop, content=list(blocks))


class FakeClient:
    """Liefert vorbereitete Antworten und merkt sich jeden Aufruf (Argumente als Momentaufnahme)."""

    def __init__(self, *script, fail_beta=False):
        self.script = list(script)
        self.calls: list[dict] = []
        self.fail_beta = fail_beta
        self.messages = NS(stream=lambda **kw: self._stream(kw, beta=False))
        self.beta = NS(messages=NS(stream=lambda **kw: self._stream(kw, beta=True)))

    @contextmanager
    def _stream(self, kw, beta):
        self.calls.append({**kw, "_beta": beta, "messages": list(kw["messages"])})
        if beta and self.fail_beta:
            raise anthropic.BadRequestError(
                "fallbacks is not enabled for this organization",
                response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None)
        nxt = self.script.pop(0)
        yield NS(get_final_message=lambda: nxt)


def make_user(db, email="c@example.com", ftp=250.0) -> User:
    u = User(email=email, password_hash="x")
    u.profile = AthleteProfile(ftp=ftp, goals="Gran Fondo im Juni")
    db.add(u)
    db.commit()
    return u


def run(db, user, client, text_="Hallo", **kw):
    return agent.run_coach(db, user, text_, [], model="claude-sonnet-5-5", client=client, **kw)


def tool_results(call) -> list[dict]:
    last = call["messages"][-1]
    assert last["role"] == "user"
    return last["content"]


# ----------------------------------------------------------------------- Agent ---


def test_tool_loop_creates_workout_and_reports_actions():
    structure = [
        {"type": "warmup", "duration_s": 600, "power_pct": [50, 70]},
        {"type": "repeat", "count": 3, "steps": [{"type": "interval", "duration_s": 900, "power_pct": [90, 92]},
                                                  {"type": "rest", "duration_s": 300, "power_pct": [55, 55]}]},
        {"type": "cooldown", "duration_s": 600, "power_pct": [60, 45]},
    ]
    fake = FakeClient(
        msg(tool("t1", "get_athlete_profile"), stop="tool_use"),
        msg(tool("t2", "create_workouts", workouts=[{"date": TOMORROW, "title": "Sweetspot 3x15", "structure": structure}]), stop="tool_use"),
        msg(text("Ich habe Dir morgen ein Sweetspot-Training eingeplant.")),
    )
    with SessionLocal() as db:
        u = make_user(db)
        r = run(db, u, fake, effort="high")
        w = db.scalar(select(PlannedWorkout))
        assert w.created_by == "coach" and w.title == "Sweetspot 3x15" and w.planned_tss > 40

    assert r["text"].startswith("Ich habe Dir morgen") and r["actions"] == ["1 Training(s) angelegt"]
    assert len(fake.calls) == 3
    first = fake.calls[0]
    assert first["model"] == "claude-sonnet-5-5" and first["output_config"] == {"effort": "high"}
    assert first["thinking"] == {"type": "adaptive"}
    assert {t["name"] for t in first["tools"]} >= {"create_workouts", "get_calendar"}
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}  # statischer Teil gecacht
    assert "Gran Fondo" in first["system"][1]["text"] and "cache_control" not in first["system"][1]
    # Ergebnis des ersten Werkzeugs wurde zurueckgegeben, mit passender id
    res = tool_results(fake.calls[1])[0]
    assert res["tool_use_id"] == "t1" and "ftp_w" in json.loads(res["content"])
    created = json.loads(tool_results(fake.calls[2])[0]["content"])
    assert created["created"][0]["date"] == TOMORROW and created["week_checks"][0]["workouts"] == 1
    assert first["_beta"] is True  # Fallback-Option standardmaessig an


def test_invalid_tool_input_is_reported_not_written():
    past = (dt.date.today() - dt.timedelta(days=2)).isoformat()
    bad_pct = {"type": "steady", "duration_s": 600, "power_pct": [300, 300]}
    fake = FakeClient(
        msg(tool("a", "create_workouts", workouts=[{"date": past, "title": "Gestern"}]), stop="tool_use"),
        msg(tool("b", "create_workouts", workouts=[{"date": TOMORROW, "title": "Zu hart", "structure": [bad_pct]}]), stop="tool_use"),
        msg(tool("c", "create_workouts", workouts="kaputt"), stop="tool_use"),
        msg(tool("d", "gibts_nicht"), stop="tool_use"),
        msg(text("Verstanden, ich korrigiere.")),
    )
    with SessionLocal() as db:
        u = make_user(db)
        r = run(db, u, fake)
        assert db.scalar(select(PlannedWorkout)) is None
    errs = [tool_results(c)[0] for c in fake.calls[1:]]
    assert all(e["is_error"] for e in errs)
    assert "Vergangenheit" in errs[0]["content"] and "20 und 250" in errs[1]["content"]
    assert "nichtleere Liste" in errs[2]["content"] and "Unbekanntes Werkzeug" in errs[3]["content"]
    assert r["actions"] == []


def test_partial_batch_is_all_or_nothing():
    ok = {"date": TOMORROW, "title": "Gut", "planned_duration_s": 3600, "planned_tss": 50}
    bad = {"date": "morgen", "title": "Schlecht"}
    fake = FakeClient(msg(tool("a", "create_workouts", workouts=[ok, bad]), stop="tool_use"), msg(text("ok")))
    with SessionLocal() as db:
        run(db, make_user(db), fake)
        assert db.scalar(select(PlannedWorkout)) is None


def test_cannot_touch_foreign_or_past_workouts():
    with SessionLocal() as db:
        owner = make_user(db, "owner@example.com")
        me = make_user(db, "me@example.com")
        foreign = PlannedWorkout(user_id=owner.id, date=dt.date.today() + dt.timedelta(days=2), title="Fremd", created_by="user")
        old = PlannedWorkout(user_id=me.id, date=dt.date.today() - dt.timedelta(days=1), title="Alt", created_by="user")
        mine = PlannedWorkout(user_id=me.id, date=dt.date.today() + dt.timedelta(days=2), title="Mein", created_by="user",
                              planned_duration_s=3600, planned_tss=60)
        db.add_all([foreign, old, mine])
        db.commit()
        fake = FakeClient(
            msg(tool("1", "delete_workout", id=foreign.id), tool("2", "update_workout", id=old.id, title="X"),
                tool("3", "update_workout", id=mine.id, title="Neu", date=TOMORROW), tool("4", "delete_workout", id="abc"), stop="tool_use"),
            msg(text("fertig")),
        )
        r = run(db, me, fake)
        res = {x["tool_use_id"]: x for x in tool_results(fake.calls[1])}
        assert res["1"]["is_error"] and res["2"]["is_error"] and res["4"]["is_error"]
        assert not res["3"].get("is_error")
        assert db.get(PlannedWorkout, foreign.id) is not None and db.get(PlannedWorkout, old.id).title == "Alt"
        assert db.get(PlannedWorkout, mine.id).title == "Neu"
        assert r["actions"] == ["Training geaendert: Neu (" + TOMORROW + ")"]


def test_week_check_warns_about_overload():
    with SessionLocal() as db:
        u = make_user(db)
        for i in range(1, 61):  # 60 Tage x 60 TSS -> CTL etwa 45, Referenz etwa 300 TSS/Woche
            db.add(Activity(user_id=u.id, source="strava", external_id=str(i), sport="Ride", tss=60.0, duration_s=3600,
                            start_time=dt.datetime.combine(dt.date.today() - dt.timedelta(days=i), dt.time(8))))
        db.commit()
        monday = dt.date.today() + dt.timedelta(days=(7 - dt.date.today().weekday()))
        week = [{"date": (monday + dt.timedelta(days=d)).isoformat(), "title": f"Hart {d}", "planned_duration_s": 7200, "planned_tss": 150}
                for d in range(7)]
        fake = FakeClient(msg(tool("a", "create_workouts", workouts=week), stop="tool_use"), msg(text("ok")))
        run(db, u, fake)
    chk = json.loads(tool_results(fake.calls[1])[0]["content"])["week_checks"][0]
    assert chk["planned_tss"] == 1050 and "warning" in chk


def test_fallback_option_is_dropped_if_rejected():
    fake = FakeClient(msg(text("Hallo")), fail_beta=True)
    with SessionLocal() as db:
        r = run(db, make_user(db), fake)
    assert r["text"] == "Hallo"
    assert [c["_beta"] for c in fake.calls] == [True, False]


def test_round_limit_and_refusal_and_errors(monkeypatch):
    monkeypatch.setattr(agent, "MAX_ROUNDS", 2)
    loop = [msg(tool(str(i), "get_athlete_profile"), stop="tool_use") for i in range(5)]
    with SessionLocal() as db:
        u = make_user(db)
        r = run(db, u, FakeClient(*loop))
        assert "nicht abschliessen" in r["text"]
        r = run(db, u, FakeClient(msg(stop="refusal")))
        assert "nicht helfen" in r["text"]
        r = run(db, u, FakeClient(msg(text("Teilantwort"), stop="max_tokens")))
        assert r["text"].startswith("Teilantwort") and "abgebrochen" in r["text"]


def test_api_errors_are_mapped():
    class Boom:
        def __init__(self, exc):
            self.exc = exc
            self.messages = NS(stream=self._raise)
            self.beta = NS(messages=NS(stream=self._raise))

        def _raise(self, **kw):
            raise self.exc

    req = httpx.Request("POST", "https://x")
    cases = [
        (anthropic.AuthenticationError("x", response=httpx.Response(401, request=req), body=None), 503),
        (anthropic.RateLimitError("x", response=httpx.Response(429, request=req), body=None), 429),
        (anthropic.APIConnectionError(request=req), 502),
        (anthropic.InternalServerError("x", response=httpx.Response(500, request=req), body=None), 502),
    ]
    with SessionLocal() as db:
        u = make_user(db)
        for exc, status in cases:
            with pytest.raises(agent.CoachError) as e:
                run(db, u, Boom(exc))
            assert e.value.status == status


# ------------------------------------------------------------------------ API ---


def test_http_endpoints(monkeypatch):
    c = TestClient(app)
    tok = c.post("/auth/register", json={"email": "api@example.com", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    s = get_settings()

    monkeypatch.setattr(s, "anthropic_api_key", "")
    assert c.get("/coach/status", headers=h).json()["configured"] is False
    assert c.post("/coach/chat", json={"message": "Hi"}, headers=h).status_code == 503

    monkeypatch.setattr(s, "anthropic_api_key", "sk-test")
    seen = []

    def fake_run(db, user, text_, history, *, model, effort, client=None):
        seen.append({"text": text_, "history": history, "model": model, "effort": effort})
        return {"text": f"Antwort {len(seen)}", "actions": ["1 Training(s) angelegt"] if len(seen) == 1 else [], "model": model}

    monkeypatch.setattr("app.routers.coach.run_coach", fake_run)
    r = c.post("/coach/chat", json={"message": "Erste Frage"}, headers=h)
    assert r.status_code == 200 and [m["role"] for m in r.json()] == ["user", "assistant"]
    assert r.json()[1]["actions"] == ["1 Training(s) angelegt"]
    assert r.json()[1]["created_at"].endswith(("Z", "+00:00"))  # Zeitzone ist angegeben
    c.post("/coach/chat", json={"message": "Zweite Frage"}, headers=h)
    assert seen[1]["history"] == [{"role": "user", "content": "Erste Frage"}, {"role": "assistant", "content": "Antwort 1"}]
    assert seen[1]["model"] == s.coach_chat_model and seen[1]["effort"] == "medium"

    c.post("/coach/quick", json={"action": "plan_week"}, headers=h)
    assert seen[2]["model"] == s.coach_planning_model and seen[2]["effort"] == "high" and "Trainingswoche" in seen[2]["text"]
    assert c.post("/coach/quick", json={"action": "unbekannt"}, headers=h).status_code == 422
    assert c.post("/coach/chat", json={"message": ""}, headers=h).status_code == 422

    msgs = c.get("/coach/messages", headers=h).json()
    assert [m["text"] for m in msgs][:2] == ["Erste Frage", "Antwort 1"] and len(msgs) == 6

    # Tageslimit
    monkeypatch.setattr(s, "coach_daily_message_limit", 3)
    assert c.post("/coach/chat", json={"message": "noch eine"}, headers=h).status_code == 429

    # Nutzer sehen nur den eigenen Verlauf; Loeschen
    tok2 = c.post("/auth/register", json={"email": "other@example.com", "password": "geheim123"}).json()["access_token"]
    assert c.get("/coach/messages", headers={"Authorization": f"Bearer {tok2}"}).json() == []
    assert c.delete("/coach/messages", headers=h).status_code == 204
    assert c.get("/coach/messages", headers=h).json() == []


def test_failed_run_leaves_no_history(monkeypatch):
    c = TestClient(app)
    tok = c.post("/auth/register", json={"email": "f@example.com", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")

    def boom(*a, **k):
        raise agent.CoachError("Keine Verbindung zur Anthropic-API.", 502)

    monkeypatch.setattr("app.routers.coach.run_coach", boom)
    r = c.post("/coach/chat", json={"message": "Hi"}, headers=h)
    assert r.status_code == 502 and "Anthropic" in r.json()["detail"]
    assert c.get("/coach/messages", headers=h).json() == []
    with SessionLocal() as db:
        assert db.scalar(select(CoachMessage)) is None


# ------------------------------------------------------------------ Formhinweis ---


def seed_rides(db, u, days_ago_from=30, days_ago_to=60):
    """Fahrten nur vor 30-60 Tagen: heute ist die Form daher hoch (lange kein Training)."""
    for i in range(days_ago_from, days_ago_to + 1):
        db.add(Activity(user_id=u.id, source="strava", external_id=str(i), sport="Ride", tss=70.0, duration_s=3600,
                        start_time=dt.datetime.combine(dt.date.today() - dt.timedelta(days=i), dt.time(8))))
    db.commit()


def add_chat(db, u, *texts):
    for i, t in enumerate(texts):
        db.add(CoachMessage(user_id=u.id, role="user" if i % 2 == 0 else "assistant", content={"text": t}))
    db.commit()


def test_form_hint_uses_chat_and_is_cached():
    from app.coach import form_hint as fh

    fh._cache.clear()
    fake = FakeClient(msg(text("Du bist bewusst in der Offseason, die hohe Frische ist gewollt.")),
                      msg(text("Zweiter Text.")))
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        add_chat(db, u, "Ich bin in der Offseason und trainiere ab dem ersten Montag im November strukturiert.",
                 "Alles klar, dann ruhig angehen.")
        t1 = fh.form_hint(db, u, client=fake)
        t2 = fh.form_hint(db, u, client=fake)  # gleicher Zustand: aus dem Zwischenspeicher
        assert t1 == t2 == "Du bist bewusst in der Offseason, die hohe Frische ist gewollt."
        assert len(fake.calls) == 1

        prompt = fake.calls[0]["messages"][0]["content"]
        assert "Offseason" in prompt and "ersten Montag im November" in prompt and "Gran Fondo" in prompt
        assert "TSB" in prompt and fake.calls[0]["model"] == get_settings().coach_chat_model
        assert "widersprechen" in fake.calls[0]["system"]

        add_chat(db, u, "Ich bin krank geworden.")  # neue Nachricht -> neuer Text
        assert fh.form_hint(db, u, client=fake) == "Zweiter Text."
        assert len(fake.calls) == 2


def test_form_hint_without_context_or_data_makes_no_call():
    from app.coach import form_hint as fh

    fh._cache.clear()
    fake = FakeClient()
    with SessionLocal() as db:
        u = make_user(db)
        u.profile.goals = None
        db.commit()
        seed_rides(db, u)
        assert fh.form_hint(db, u, client=fake) is None  # weder Gespraech noch Ziele
        add_chat(db, u, "Hallo")
        db.query(Activity).delete()
        db.commit()
        assert fh.form_hint(db, u, client=fake) is None  # keine Trainingsdaten
    assert fake.calls == []


def test_form_hint_errors_return_none_and_are_not_cached():
    from app.coach import form_hint as fh

    fh._cache.clear()

    @contextmanager
    def boom(**kw):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
        yield

    broken = NS(messages=NS(stream=boom))
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        add_chat(db, u, "Offseason bis November.")
        assert fh.form_hint(db, u, client=broken) is None
        ok = FakeClient(msg(text("**Ruhig** angehen.")))
        assert fh.form_hint(db, u, client=ok) == "Ruhig angehen."  # Fehler wurde nicht gemerkt, Markdown entfernt


def test_form_hint_text_is_shortened_cleanly():
    from app.coach.form_hint import MAX_LEN, _clean

    long = "Das ist ein Satz. " * 40
    out = _clean(long)
    assert len(out) <= MAX_LEN and out.endswith(".")
    assert _clean("Eins   \n zwei") == "Eins zwei"


def test_form_hint_endpoint(monkeypatch):
    from app.coach import form_hint as fh

    fh._cache.clear()
    c = TestClient(app)
    tok = c.post("/auth/register", json={"email": "hint@example.com", "password": "geheim123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get("/coach/form-hint").status_code == 401
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    assert c.get("/coach/form-hint", headers=h).json() == {"text": None}
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    monkeypatch.setattr("app.routers.coach.form_hint", lambda db, user: "Offseason ist gewollt.")
    assert c.get("/coach/form-hint", headers=h).json() == {"text": "Offseason ist gewollt."}


# -------------------------------------------------------------------- Gedaechtnis ---

IN_10_DAYS = (dt.date.today() + dt.timedelta(days=10)).isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def test_coach_saves_updates_and_forgets_memories_on_its_own():
    from app.models import CoachMemory

    fake = FakeClient(
        msg(tool("m1", "save_memory", text="Offseason, strukturiertes Training ab Montag im November.", valid_until=IN_10_DAYS),
            tool("m2", "save_memory", text="Trainiert am liebsten morgens."), stop="tool_use"),
        msg(text("Habe ich mir gemerkt.")),
    )
    with SessionLocal() as db:
        u = make_user(db)
        r = run(db, u, fake, "Ich bin in der Offseason und fahre lieber morgens.")
        mems = db.scalars(select(CoachMemory).order_by(CoachMemory.id)).all()
        assert [m.text for m in mems] == ["Offseason, strukturiertes Training ab Montag im November.", "Trainiert am liebsten morgens."]
        assert mems[0].valid_until.isoformat() == IN_10_DAYS and mems[1].valid_until is None
        assert r["actions"][0].startswith("Gemerkt: Offseason") and len(r["actions"]) == 2

        # Naechste Anfrage: Gedaechtnis steht im Kontext (mit ids), Aktualisieren und Vergessen funktionieren
        fake2 = FakeClient(
            msg(tool("u", "save_memory", id=mems[1].id, text="Trainiert am liebsten abends."),
                tool("f", "forget_memory", id=mems[0].id), stop="tool_use"),
            msg(text("Angepasst.")),
        )
        r2 = run(db, u, fake2, "Doch lieber abends, und die Offseason ist vorbei.")
        ctx = fake2.calls[0]["system"][1]["text"]
        assert f"[{mems[0].id}] Offseason" in ctx and f"(gilt bis {IN_10_DAYS})" in ctx and "Gedaechtnis" in ctx
        left = db.scalars(select(CoachMemory)).all()
        assert [m.text for m in left] == ["Trainiert am liebsten abends."]
        assert r2["actions"][1].startswith("Vergessen: Offseason")
    assert "Gedaechtnis" in fake.calls[0]["system"][0]["text"]  # Anweisung im (gecachten) Systemprompt
    assert {t["name"] for t in fake.calls[0]["tools"]} >= {"save_memory", "forget_memory"}


def test_memory_tool_validation_dedup_limit_and_isolation():
    from app.coach import tools as T
    from app.models import CoachMemory

    with SessionLocal() as db:
        a = make_user(db, "a@example.com")
        b = make_user(db, "b@example.com")
        first = T.save_memory(db, a, {"text": "Mag keine Rolle  ", "valid_until": IN_10_DAYS})
        again = T.save_memory(db, a, {"text": "mag keine rolle"})  # gleicher Fakt, andere Schreibweise
        assert again["note"] == "Eintrag existierte bereits" and db.query(CoachMemory).count() == 1
        assert first["saved"].endswith(f"(gilt bis {IN_10_DAYS})")

        for bad, msg_part in [({"text": ""}, "leer"), ({"text": "x" * 301}, "laenger"),
                              ({"text": "ok", "valid_until": YESTERDAY}, "Vergangenheit"),
                              ({"text": "ok", "valid_until": "morgen"}, "kein Datum"),
                              ({"text": "ok", "id": 999}, "nicht gefunden")]:
            with pytest.raises(T.ToolError, match=msg_part):
                T.save_memory(db, a, bad)

        mem_id = db.scalar(select(CoachMemory.id))
        with pytest.raises(T.ToolError, match="nicht gefunden"):  # fremder Nutzer
            T.save_memory(db, b, {"text": "gehackt", "id": mem_id})
        with pytest.raises(T.ToolError, match="nicht gefunden"):
            T.forget_memory(db, b, {"id": mem_id})
        assert db.get(CoachMemory, mem_id).text == "Mag keine Rolle"

        for i in range(T.MAX_MEMORIES - 1):
            T.save_memory(db, a, {"text": f"Fakt {i}"})
        with pytest.raises(T.ToolError, match="voll"):
            T.save_memory(db, a, {"text": "Einer zu viel"})
        T.save_memory(db, a, {"text": "Ersetzt", "id": mem_id})  # Aktualisieren geht auch bei vollem Gedaechtnis
        assert db.get(CoachMemory, mem_id).valid_until is None
        assert T.active_memories(db, b.id) == []


def test_expired_memories_are_ignored():
    from app.coach import tools as T
    from app.models import CoachMemory

    with SessionLocal() as db:
        u = make_user(db)
        db.add_all([CoachMemory(user_id=u.id, text="Alt", valid_until=dt.date.today() - dt.timedelta(days=1)),
                    CoachMemory(user_id=u.id, text="Heute noch gueltig", valid_until=dt.date.today()),
                    CoachMemory(user_id=u.id, text="Dauerhaft")])
        db.commit()
        assert [m.text for m in T.active_memories(db, u.id)] == ["Heute noch gueltig", "Dauerhaft"]
        assert "Alt" not in agent.build_context(db, u).split("Gedaechtnis")[1]
        assert "noch leer" in agent.build_context(db, make_user(db, "leer@example.com"))


def test_memory_endpoints():
    from app.models import CoachMemory

    c = TestClient(app)
    h1 = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "m1@example.com", "password": "geheim123"}).json()["access_token"]}
    h2 = {"Authorization": "Bearer " + c.post("/auth/register", json={"email": "m2@example.com", "password": "geheim123"}).json()["access_token"]}
    assert c.get("/coach/memories").status_code == 401
    with SessionLocal() as db:
        uid = db.scalar(select(User.id).where(User.email == "m1@example.com"))
        db.add_all([CoachMemory(user_id=uid, text="Offseason", valid_until=dt.date.today() + dt.timedelta(days=3)),
                    CoachMemory(user_id=uid, text="Abgelaufen", valid_until=dt.date.today() - dt.timedelta(days=3))])
        db.commit()
    got = c.get("/coach/memories", headers=h1).json()
    assert [m["text"] for m in got] == ["Offseason"] and got[0]["valid_until"] == (dt.date.today() + dt.timedelta(days=3)).isoformat()
    assert c.get("/coach/memories", headers=h2).json() == []
    assert c.delete(f"/coach/memories/{got[0]['id']}", headers=h2).status_code == 404  # fremder Eintrag
    assert c.delete(f"/coach/memories/{got[0]['id']}", headers=h1).status_code == 204
    assert c.get("/coach/memories", headers=h1).json() == []


def test_form_hint_uses_memory_even_without_chat_or_goals():
    from app.coach import form_hint as fh
    from app.coach import tools as T

    fh._cache.clear()
    fake = FakeClient(msg(text("Offseason: die hohe Frische ist gewollt.")))
    with SessionLocal() as db:
        u = make_user(db)
        u.profile.goals = None
        db.commit()
        seed_rides(db, u)
        assert fh.form_hint(db, u, client=FakeClient()) is None  # ohne Gedaechtnis kein Kontext
        T.save_memory(db, u, {"text": "Offseason bis zum ersten Montag im November.", "valid_until": IN_10_DAYS})
        assert fh.form_hint(db, u, client=fake) == "Offseason: die hohe Frische ist gewollt."
    assert "Offseason bis zum ersten Montag" in fake.calls[0]["messages"][0]["content"]


def test_form_hint_truncated_text_is_cut_to_last_full_sentence():
    from app.coach import form_hint as fh

    fh._cache.clear()
    cut = FakeClient(msg(text("Die Offseason ist gewollt. Genieß die Pause mit lockeren Fahrten, am ersten Mont"), stop="max_tokens"),
                     msg(text("Halber Satz ohne Ende"), stop="max_tokens"))
    with SessionLocal() as db:
        u = make_user(db)
        seed_rides(db, u)
        add_chat(db, u, "Offseason bis November.")
        assert fh.form_hint(db, u, client=cut) == "Die Offseason ist gewollt."  # nie ein halber Satz
        k = cut.calls[0]
        # "disabled" lehnt das Modell mit 400 ab, deshalb between_tools; grosses Limit gegen Abbrueche
        assert k["thinking"] == {"type": "between_tools"} and k["max_tokens"] >= 4000
        fh._cache.clear()
        assert fh.form_hint(db, u, client=cut) is None  # gar kein vollstaendiger Satz: Standardtext der App


def test_coach_creates_strength_workout():
    structure = [
        {"type": "exercise", "name": "Kniebeuge", "sets": 3, "reps": 8, "rest_s": 120, "load": "RPE 7"},
        {"type": "exercise", "name": "Plank", "sets": 3, "duration_s": 45, "rest_s": 30},
    ]
    fake = FakeClient(
        msg(tool("t1", "create_workouts", workouts=[{"date": TOMORROW, "title": "Kraft Beine und Rumpf", "structure": structure}]), stop="tool_use"),
        msg(text("Ich habe Dir morgen ein Krafttraining eingeplant.")),
    )
    with SessionLocal() as db:
        u = make_user(db)
        r = run(db, u, fake)
        w = db.scalar(select(PlannedWorkout))
        assert w.created_by == "coach" and w.planned_tss is None and w.planned_duration_s == 597
        assert w.structure[0]["name"] == "Kniebeuge" and w.structure[1]["duration_s"] == 45
    assert r["actions"] == ["1 Training(s) angelegt"]
    assert "Krafttraining" in agent.SYSTEM_PROMPT
