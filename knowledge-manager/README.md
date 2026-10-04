# Wissens-Manager

Desktop-Programm für die Wissensbasis des Coaches: Recherche starten, Ergebnisse mit KI-Zusammenfassung bewerten
(aufnehmen, Watchlist, verwerfen) und in die gemeinsame Datenbank des Backends schreiben.

## Einrichten

1. In `backend/.env` einen langen, zufälligen `KNOWLEDGE_ADMIN_TOKEN` setzen und das Backend neu starten.
2. Einmal im Terminal `claude` starten und mit dem Abo anmelden. Das Programm nutzt `claude -p`, ohne API-Schlüssel.
3. Programm starten (`python -m wissens_manager` im Entwicklungs-venv oder `Wissens-Manager.exe`), unter
   Datei → Einstellungen Backend-Adresse und Schlüssel eintragen, „Verbindungen testen“.

## Entwickeln

```
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
build.bat          # baut dist\Wissens-Manager
```

Regeln: Evidenzstufen, Belegzitate und Pflichtfelder prüft das Backend (`backend/app/knowledge.py`). Das Programm prüft
zusätzlich, dass jedes Belegzitat wörtlich im Abstract steht, und gleicht Rückzüge über Europe PMC und Crossref ab.
