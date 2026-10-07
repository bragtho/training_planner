from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite fuer lokale Entwicklung, in Produktion z. B. postgresql+psycopg://...
    database_url: str = "sqlite:///./training.db"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24 * 7
    # Fernet-Key zum Verschluesseln der OAuth-Tokens (python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    token_encryption_key: str = ""

    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_verify_token: str = "change-me"
    wahoo_client_id: str = ""
    wahoo_client_secret: str = ""

    anthropic_api_key: str = ""
    coach_chat_model: str = "claude-sonnet-5-5"
    coach_planning_model: str = "claude-opus-5-5"
    # Bei Ablehnung durch die Sicherheitsfilter uebernimmt serverseitig ein Ersatzmodell
    coach_refusal_fallback: bool = True
    coach_daily_message_limit: int = 100
    # Obergrenze fuer Trainings-Feedback je Tag (ein Modellaufruf je Fahrt)
    coach_feedback_daily_limit: int = 30
    # Schluessel fuer die Verwaltungs-Schnittstelle der Wissensbasis (Wissens-Manager); leer = Schnittstelle gesperrt
    knowledge_admin_token: str = ""

    public_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
