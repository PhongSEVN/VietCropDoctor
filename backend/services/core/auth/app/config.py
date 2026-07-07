from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_dsn: str = "postgresql://vcdauth:secret@postgres:5432/vcd_auth"
    redis_url: str = "redis://redis:6379/1"   # DB 1 separates auth tokens from app cache

    # Actual JWT signing/expiry lives in vcd_shared.auth.JWTConfig (reads
    # JWT_SECRET/ACCESS_TOKEN_EXPIRE_MINUTES/REFRESH_TOKEN_EXPIRE_DAYS from the
    # environment directly). These two fields only size the auth cookies'
    # max-age and must stay numerically in sync with that env config.
    access_token_expire_minutes: int = 1440   # 24h
    refresh_token_expire_days: int = 30

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    log_level: str = "INFO"
    minio_public_url: str = "http://localhost:9002"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
