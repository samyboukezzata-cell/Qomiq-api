"""
Qomiq API — Configuration centralisée (pydantic-settings).
Charge les variables depuis .env ou l'environnement système.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Base de données
    DATABASE_URL: str = "sqlite:///./qomiq_dev.db"

    # JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    ALLOWED_ORIGINS: str = "https://qomiq.fr,http://localhost:3000,https://qomiq-web.vercel.app"
    ENVIRONMENT: str = "development"

    # App
    APP_NAME: str = "Qomiq API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
