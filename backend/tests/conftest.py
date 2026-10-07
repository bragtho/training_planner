"""Test-Umgebung: vor jedem Import der App setzen, damit weder .env noch echte Dienste genutzt werden."""

import os

from cryptography.fernet import Fernet

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"
os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["STRAVA_CLIENT_ID"] = "123"
os.environ["STRAVA_CLIENT_SECRET"] = "shh"
os.environ["STRAVA_VERIFY_TOKEN"] = "verify-me"
os.environ["PUBLIC_BASE_URL"] = "http://localhost:8000"
os.environ["ANTHROPIC_API_KEY"] = ""  # nie echte Modellaufrufe aus Tests (auch nicht aus Hintergrundaufgaben)
