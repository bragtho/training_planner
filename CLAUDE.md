# CLAUDE.md

Regeln für die Arbeit an diesem Projekt (Radtrainings-Plattform mit KI-Coach).

## Regeln

### Änderungen immer in einem separaten Branch

- Nie direkt auf `master` ändern. Vor der ersten Änderung prüfen, auf welchem Branch Du bist (`git branch --show-current`). Bist Du auf `master`, zuerst einen neuen Branch anlegen.
- Ein Branch pro Änderung oder Thema. Nicht auf einem Branch weiterarbeiten, dessen Thema schon abgeschlossen oder gemergt ist.
- Branch-Name: `<typ>/<kurzbeschreibung>` in Kleinbuchstaben mit Bindestrichen, z. B. `feature/wahoo-export`, `fix/strava-token-refresh`, `docs/claude-md`. Typen: `feature`, `fix`, `docs`, `chore`, `refactor`.
- Commit, Push, Pull Request und Merge nur auf ausdrückliche Anfrage.

### Semantische Versionierung

Es gilt [Semantic Versioning 2.0.0](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH`.

- **MAJOR:** Inkompatible Änderungen. Beim Backend z. B. entfernte oder geänderte API-Endpunkte, ein Datenbankschema ohne Migration oder ein geändertes Format der Workout-Struktur. Bei der App z. B. entfernte Funktionen oder ein Wechsel, der gespeicherte Daten auf dem Gerät unbrauchbar macht.
- **MINOR:** Neue Funktion, die bestehendes Verhalten nicht bricht.
- **PATCH:** Fehlerbehebungen ohne neue Funktion und ohne Änderung der Schnittstellen.
- Solange die Version `0.y.z` ist, gilt die Komponente als in früher Entwicklung. Dann darf auch ein MINOR-Sprung etwas Bestehendes ändern.
- **Backend, App und Wissens-Manager werden unabhängig voneinander versioniert.** Jede Komponente hat ihre eigene Version und steigt nur, wenn sich ihr eigener Ordner ändert:
  - Backend: `backend/pyproject.toml` (`version`)
  - App: `app/pubspec.yaml` (`version: X.Y.Z+BUILD`). Die Build-Nummer hinter dem `+` zählt bei jedem App-Release hoch.
  - Wissens-Manager: `knowledge-manager/pyproject.toml` (`version`) und `knowledge-manager/wissens_manager/__init__.py` (`__version__`), beide immer gleich.
- Ändert eine Änderung beide Ordner, bekommt jede Komponente ihre eigene Stufe nach ihrer eigenen Auswirkung. Eine neue API-Funktion ist z. B. MINOR im Backend und MINOR in der App, wenn die App sie nutzt.
- Eine inkompatible Backend-Änderung (MAJOR) wird im Commit-Text oder der Beschreibung ausdrücklich benannt, damit klar bleibt, welche App-Version dazu passt.
- Ein Release ist ein Git-Tag auf dem gemergten Stand, getrennt je Komponente: `backend-vX.Y.Z`, `app-vX.Y.Z` und `wissensmanager-vX.Y.Z`. Der Versionssprung kommt in einen eigenen Commit.
- Bei einer Änderung nenne je betroffener Komponente die passende Stufe (MAJOR, MINOR oder PATCH) und begründe sie in einem Satz. Version erhöhen und taggen nur nach Bestätigung.

## Projekt

- `backend/`: Python-API (FastAPI, SQLAlchemy). Tests in `backend/tests`.
- `app/`: Flutter-App (Web und Android).
- `knowledge-manager/`: Wissens-Manager, Desktop-Programm (PyQt6, mit PyInstaller als Ordner gebaut) für Recherche, KI-Bewertung und Freigabe von Studien. Schreibt über die Verwaltungs-Schnittstelle des Backends (`/knowledge/admin/*`, Schlüssel `KNOWLEDGE_ADMIN_TOKEN`) in die Wissensbasis. Die KI-Auswertung läuft über `claude -p` mit der Abo-Anmeldung, nicht über die API. Inhalte der Wissensbasis liegen in der Datenbank, nicht in Git.
- Backend testen (im Ordner `backend/`): `.venv/Scripts/python -m pytest -q`
- App prüfen (im Ordner `app/`): `flutter analyze` und `flutter test`
- Wissens-Manager testen (im Ordner `knowledge-manager/`, eigenes venv): `.venv/Scripts/python -m pytest -q`; bauen: `build.bat` (Ergebnis in `dist/Wissens-Manager`); Selbsttest der gebauten Datei: `dist/Wissens-Manager/Wissens-Manager.exe --selftest` schreibt `selftest.txt`.
- Geheimnisse (API-Schlüssel, Tokens) stehen nur in `backend/.env`, die nicht ins Repository gehört. Eine Ausnahme: Der Wissens-Manager speichert den Verwaltungsschlüssel in `knowledge-manager/config.json` (steht in `.gitignore`).
