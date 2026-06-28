from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Downstream services
    vision_ai_url: str = "http://vision-ai:8001"
    rag_engine_url: str = "http://rag-engine:8002"
    ollama_base_url: str = "http://ollama:11434"

    # Reasoning LLM (Ollama model tag)
    reasoning_model: str = "qwen2.5:7b"
    reasoning_temperature: float = 0.2
    reasoning_timeout_seconds: int = 60

    # Auth
    jwt_secret: str = "change-me-in-production-use-64-char-random"
    jwt_algorithm: str = "HS256"

    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
