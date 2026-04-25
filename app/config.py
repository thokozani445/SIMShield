from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Server
    app_env: str = "development"
    app_port: int = 8000
    app_version: str = "1.0.0-hackathon"

    # Security
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # CAMARA / Nokia
    mock_mode: bool = True
    nokia_api_base_url: str = "https://network-as-code.nokia.com"
    nokia_client_id: str = ""
    nokia_client_secret: str = ""
    nokia_token_url: str = ""

    # AI Orchestrator
    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-4-20250514"
    agent_max_tokens: int = 1000

    # Database
    database_url: str = "sqlite+aiosqlite:///./simshield.db"

    # CORS
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()