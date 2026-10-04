"""Verwaltungs-Schnittstelle des Backends (/knowledge/admin/*): die gemeinsame Datenbank mit dem Coach."""

from __future__ import annotations

from typing import Any

import httpx


class BackendError(Exception):
    """Meldung fuer den Nutzer (Backend nicht erreichbar, Schluessel falsch, Karte ungueltig ...)."""


class BackendClient:
    def __init__(self, base_url: str, token: str, http: httpx.Client | None = None):
        self.base = base_url.rstrip("/") + "/knowledge/admin"
        self.http = http or httpx.Client(timeout=30)
        self.headers = {"X-Admin-Token": token}

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = self.http.request(method, self.base + path, headers=self.headers, **kw)
        except httpx.HTTPError as e:
            raise BackendError(f"Backend nicht erreichbar ({e.__class__.__name__}). Läuft es, und stimmt die Adresse in den Einstellungen?") from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            if r.status_code == 401:
                detail = "Der Verwaltungsschlüssel stimmt nicht mit KNOWLEDGE_ADMIN_TOKEN im Backend überein."
            raise BackendError(str(detail))
        return None if r.status_code == 204 else r.json()

    def ping(self) -> dict:
        """Prueft Erreichbarkeit und Schluessel; gibt die Zahl bekannter Studien zurueck."""
        k = self.known()
        return {"dois": len(k["dois"]), "pmids": len(k["pmids"])}

    def known(self) -> dict:
        return self._request("GET", "/known")

    def ingest(self, items: list[dict]) -> dict:
        return self._request("POST", "/candidates", json={"items": items})

    def candidates(self, status: str | None = None) -> list[dict]:
        return self._request("GET", "/candidates", params={"status": status} if status else None)

    def decide(self, candidate_id: int, action: str, note: str | None = None, card: dict | None = None,
               sources: list[dict] | None = None) -> dict:
        return self._request("POST", f"/candidates/{candidate_id}/decide",
                             json={"action": action, "note": note, "card": card, "sources": sources})

    def cards(self, status: str | None = None) -> list[dict]:
        return self._request("GET", "/cards", params={"status": status} if status else None)

    def card(self, slug: str) -> dict:
        return self._request("GET", f"/cards/{slug}")

    def put_card(self, slug: str, body: dict) -> dict:
        return self._request("PUT", f"/cards/{slug}", json=body)

    def retire(self, slug: str, note: str | None = None) -> dict:
        return self._request("POST", f"/cards/{slug}/retire", json={"note": note})

    def history(self, slug: str) -> list[dict]:
        return self._request("GET", f"/cards/{slug}/history")

    def sources(self) -> list[dict]:
        return self._request("GET", "/sources")

    def export(self) -> dict:
        return self._request("GET", "/export")
