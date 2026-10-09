# training_planner

## Zugriff von unterwegs (Tailscale)

1. Tailscale auf PC und Handy installieren und mit demselben Konto anmelden.
2. Backend im Ordner `backend/` für das Netzwerk starten: `.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. Windows-Firewall: eingehend TCP 8000 erlauben (z. B. nur für das Tailscale-Netz `100.64.0.0/10`).
4. **Android-App:** Beim Anmelden unter „Server" die Adresse `http://<Tailscale-IP>:8000` eintragen (IP aus der Tailscale-App, `100.x.y.z`). Die Adresse wird gespeichert.
5. **Web-App:** Mit `flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080` oder einem gebauten `build/web` bereitstellen und im Handy-Browser `http://<Tailscale-IP>:8080` öffnen. Die Server-Adresse wird dann automatisch auf denselben Host (Port 8000) gesetzt.
6. Optional HTTPS: `tailscale serve --bg 8000` stellt das Backend unter `https://<pc>.<tailnet>.ts.net` bereit; diese Adresse dann in der App eintragen.
