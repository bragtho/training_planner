from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

_url = get_settings().database_url
engine = create_engine(_url, connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_columns() -> list[str]:
    """Legt Spalten an, die das Modell kennt, die in einer bestehenden Tabelle aber fehlen (nur additiv, immer NULL erlaubt).

    Ersatz fuer Migrationen, solange es keine gibt: neue Tabellen legt create_all an, neue Spalten diese Funktion."""
    added: list[str] = []
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                if not col.nullable and col.default is None and col.server_default is None:
                    raise RuntimeError(f"Neue Spalte {table.name}.{col.name} braucht einen Standardwert oder NULL")
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(engine.dialect)}'))
                added.append(f"{table.name}.{col.name}")
    return added


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
