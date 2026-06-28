from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql://vcdauth:secret@postgres:5432/vcd_auth"
    redis_url: str = "redis://redis:6379/1"   # DB 1 separates auth tokens from app cache

    jwt_secret: str = "change-me-in-production-use-64-char-random"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 52560000   # 100 years
    refresh_token_expire_days: int = 36500         # 100 years

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    log_level: str = "INFO"
    minio_public_url: str = "http://localhost:9002"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
