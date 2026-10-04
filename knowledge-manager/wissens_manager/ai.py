"""KI-Anbindung ueber das Claude-Programm (`claude -p`) mit der Abo-Anmeldung, ohne API-Schluessel.

Wichtig (laut Dokumentation von Claude Code): Ohne `--bare` nutzt `claude -p` die Abo-Anmeldung. Ein gesetzter
ANTHROPIC_API_KEY wuerde sie ueberschreiben und Kosten verursachen, deshalb wird er fuer den Unterprozess entfernt.
Der Aufruf laeuft in einem leeren Ordner ohne Werkzeuge, damit weder Projektdateien noch Hooks eine Rolle spielen und
das Modell nur den uebergebenen Text sieht.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

from . import prompts
from .europepmc import Paper

_LIMIT_HINTS = ("usage limit", "rate limit", "limit reached", "quota", "overloaded", "429", "credit")


class AiError(Exception):
    """KI-Aufruf fehlgeschlagen (Meldung fuer den Nutzer)."""


class AiLimitError(AiError):
    """Die Abo-Grenze ist erreicht; spaeter erneut versuchen."""


class AiAdapter(Protocol):
    def run_json(self, system: str, prompt: str, schema: dict) -> dict: ...


def parse_cli_output(stdout: str) -> tuple[dict, dict]:
    """Zerlegt die JSON-Ausgabe von `claude -p --output-format json` in (Ergebnisobjekt, Verbrauch)."""
    try:
        data = json.loads(stdout)
    except ValueError as e:
        raise AiError(f"Unlesbare Ausgabe des Claude-Programms: {stdout[:200]!r}") from e
    if isinstance(data, list):  # stream-json-aehnliche Liste: letztes result-Objekt nehmen
        data = next((d for d in reversed(data) if isinstance(d, dict) and d.get("type") == "result"), {})
    if not isinstance(data, dict):
        raise AiError("Unerwartete Ausgabe des Claude-Programms")
    usage = {"cost_usd": data.get("total_cost_usd"), **(data.get("usage") or {})}
    result_text = str(data.get("result") or "")
    if data.get("is_error"):
        msg = result_text or "Unbekannter Fehler"
        if any(h in msg.lower() for h in _LIMIT_HINTS):
            raise AiLimitError(f"Abo-Grenze erreicht oder Dienst ausgelastet: {msg[:200]}. Bitte später erneut versuchen.")
        raise AiError(f"Claude meldet einen Fehler: {msg[:300]}")
    payload = data.get("structured_output")
    if payload is None:
        text = result_text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):] if "{" in text else text
        try:
            payload = json.loads(text)
        except ValueError as e:
            raise AiError("Die Antwort enthielt kein gültiges JSON") from e
    if not isinstance(payload, dict):
        raise AiError("Die Antwort hatte nicht die erwartete Form")
    return payload, usage


class ClaudeCliAdapter:
    """Ruft `claude -p` auf (Abo, keine Werkzeuge, strukturierte Ausgabe per JSON-Schema)."""

    def __init__(self, claude_path: str = "claude", model: str = "sonnet", timeout: int = 300, retries: int = 2):
        self.claude_path = shutil.which(claude_path) or claude_path
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.last_usage: dict[str, Any] = {}
        self.total_cost_usd = 0.0
        self.calls = 0
        self._cwd = Path(tempfile.gettempdir()) / "wissens-manager-ki"
        self._cwd.mkdir(exist_ok=True)

    def available(self) -> str | None:
        """Version des Claude-Programms oder None, wenn nicht startbar."""
        try:
            out = subprocess.run([self.claude_path, "--version"], capture_output=True, text=True, timeout=20, **self._flags())
            return out.stdout.strip() or None if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _flags() -> dict:
        return {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

    def command(self, system: str, schema: dict) -> list[str]:
        return [self.claude_path, "-p", "--output-format", "json", "--json-schema", json.dumps(schema, ensure_ascii=False),
                "--tools", "", "--model", self.model, "--append-system-prompt", system]

    def run_json(self, system: str, prompt: str, schema: dict) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                proc = subprocess.run(self.command(system, schema), input=prompt, capture_output=True, text=True, encoding="utf-8",
                                      timeout=self.timeout, cwd=self._cwd, env=env, **self._flags())
            except FileNotFoundError as e:
                raise AiError(f"Claude-Programm nicht gefunden ({self.claude_path}). Pfad in den Einstellungen prüfen.") from e
            except subprocess.TimeoutExpired as e:
                last = AiError(f"Zeitüberschreitung nach {self.timeout} s")
                time.sleep(2 * (attempt + 1))
                continue
            if proc.returncode != 0 and not proc.stdout.strip():
                msg = (proc.stderr or "").strip()[:300]
                if any(h in msg.lower() for h in _LIMIT_HINTS):
                    raise AiLimitError(f"Abo-Grenze erreicht oder Dienst ausgelastet: {msg}. Bitte später erneut versuchen.")
                last = AiError(f"Claude-Programm beendete sich mit Code {proc.returncode}: {msg}")
                time.sleep(2 * (attempt + 1))
                continue
            payload, usage = parse_cli_output(proc.stdout)  # AiLimitError/AiError werden nicht wiederholt
            self.last_usage = usage
            self.calls += 1
            self.total_cost_usd += float(usage.get("cost_usd") or 0)
            return payload
        raise last or AiError("KI-Aufruf fehlgeschlagen")


# ------------------------------------------------------------ Schritte ---


def _clean_triage(raw: dict) -> dict:
    """Bringt ein KI-Ergebnis in eine sichere Form (unbekannte Werte werden zu vorsichtigen Standardwerten)."""
    out = dict(raw)
    out["relevant"] = bool(raw.get("relevant"))
    out["design"] = raw.get("design") if raw.get("design") in prompts.DESIGNS else "other"
    out["directness"] = raw.get("directness") if raw.get("directness") in prompts.DIRECTNESS else "indirect"
    out["suggested_action"] = raw.get("suggested_action") if raw.get("suggested_action") in prompts.ACTIONS else "watch"
    out["evidence_suggestion"] = raw.get("evidence_suggestion") if raw.get("evidence_suggestion") in ("A", "B", "C") else "C"
    out["quotes"] = [q.strip() for q in (raw.get("quotes") or []) if isinstance(q, str) and q.strip()][:3]
    n = raw.get("sample_n")
    out["sample_n"] = n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None
    for k in ("relevance_reason", "population", "summary", "finding", "limitations"):
        out[k] = str(raw.get(k) or "").strip()
    out["target_card"] = raw.get("target_card") or None
    if not out["relevant"] or out["suggested_action"] == "irrelevant":
        out["suggested_action"] = "irrelevant"
        out["relevant"] = False
    if out["suggested_action"] != "new_card":
        out["card_draft"] = None
    return out


def triage(adapter: AiAdapter, topic_label: str, existing: list[dict], papers: dict[str, Paper]) -> dict[str, dict]:
    """KI-Schritt 1: Bewertung und Zusammenfassung. Gibt je Studien-ID ein bereinigtes Ergebnis zurueck."""
    payload = adapter.run_json(prompts.TRIAGE_SYSTEM, prompts.triage_prompt(topic_label, existing, papers), prompts.TRIAGE_SCHEMA)
    out: dict[str, dict] = {}
    for r in payload.get("results") or []:
        if isinstance(r, dict) and r.get("id") in papers:
            out[r["id"]] = _clean_triage(r)
    return out


def cross_check(adapter: AiAdapter, items: dict[str, tuple[Paper, dict]]) -> dict[str, dict]:
    """KI-Schritt 2: Gegenpruefung jeder Aussage gegen den Abstract."""
    if not items:
        return {}
    payload = adapter.run_json(prompts.CROSS_SYSTEM, prompts.cross_prompt(items), prompts.CROSS_SCHEMA)
    out: dict[str, dict] = {}
    for r in payload.get("results") or []:
        if isinstance(r, dict) and r.get("id") in items:
            issues = [str(i) for i in (r.get("issues") or []) if str(i).strip()]
            out[r["id"]] = {"verdict": "ok" if r.get("verdict") == "ok" and not issues else "issues", "issues": issues}
    return out
