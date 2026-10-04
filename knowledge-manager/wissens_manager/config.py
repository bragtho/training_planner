"""Einstellungen des Programms: eine JSON-Datei neben dem Programm (bzw. im Projektordner bei der Entwicklung)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def app_dir() -> Path:
    """Ordner des Programms: bei PyInstaller neben der exe, sonst der Projektordner."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    override = os.environ.get("WISSENS_MANAGER_CONFIG")
    return Path(override) if override else app_dir() / "config.json"


@dataclass
class Config:
    backend_url: str = "http://localhost:8000"
    admin_token: str = ""  # entspricht KNOWLEDGE_ADMIN_TOKEN in backend/.env
    claude_path: str = "claude"  # Programm der Claude-Code-Anmeldung (Abo)
    model: str = "sonnet"
    parallel: int = 2  # gleichzeitige KI-Aufrufe (hoechstens 3)
    batch_size: int = 5  # Abstracts je KI-Aufruf
    max_papers: int = 20  # neue Studien je Recherche
    ai_timeout: int = 300  # Sekunden je KI-Aufruf
    theme: str = "dark"  # dark | light | system

    def clamp(self) -> "Config":
        self.parallel = min(max(int(self.parallel), 1), 3)
        self.batch_size = min(max(int(self.batch_size), 1), 8)
        self.max_papers = min(max(int(self.max_papers), 1), 100)
        self.ai_timeout = min(max(int(self.ai_timeout), 30), 1800)
        self.backend_url = self.backend_url.strip().rstrip("/")
        if self.theme not in ("dark", "light", "system"):
            self.theme = "dark"
        return self


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(Config)}
            for k, v in data.items():
                if k in known:
                    setattr(cfg, k, v)
        except (OSError, ValueError):
            pass  # kaputte Datei: mit Standardwerten starten, beim Speichern wird sie ersetzt
    return cfg.clamp()


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or config_path()
    path.write_text(json.dumps(asdict(cfg.clamp()), indent=2, ensure_ascii=False), encoding="utf-8")
