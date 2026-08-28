from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = "dev-secret"
    jwt_expire_hours: int = 72

    database_url: str = "mysql+pymysql://root:knowbase_dev@localhost:3306/knowbase?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"

    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5

    upload_dir: str = "uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()
