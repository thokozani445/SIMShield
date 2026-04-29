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

    # CAMARA mode
    mock_mode: bool = True

    # RapidAPI / Nokia Network-as-Code
    rapidapi_key: str = ""

    rapidapi_host_sim_swap: str = ""
    rapidapi_host_number_verification: str = ""
    rapidapi_host_device_status: str = ""
    rapidapi_host_location_verification: str = ""

    rapidapi_url_sim_swap: str = ""
    rapidapi_url_number_verification: str = ""
    rapidapi_url_device_status: str = ""
    rapidapi_url_location_verification: str = ""

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