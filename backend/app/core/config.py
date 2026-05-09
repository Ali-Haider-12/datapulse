from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    PROJECT_NAME: str = "DataPulse"
    VERSION: str = "2.1.0"

    # Google Cloud / Gemini
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_API_KEY: str = ""

    # Elasticsearch
    ES_URL: str = ""
    ES_API_KEY: str = ""

    # MCP Server (Agent Builder)
    MCP_SERVER_URL: str = "http://localhost:8080"
    MCP_API_KEY: str = ""

    # OpenRouter (LLM fallback)
    OPENROUTER_API_KEY: str = ""

    # GitHub
    GITHUB_TOKEN: str = ""

    # Twilio (Voice)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""

    # Gmail
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""

    # Cache
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 120
    REDIS_URL: str = ""

    # Session
    SESSION_TTL_HOURS: int = 24

    # Patrol
    PATROL_INTERVAL_SECONDS: int = 60

    # Health
    HEALTH_CHECK_INTERVAL_SECONDS: int = 60
    ALERT_THRESHOLD_SCORE: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()