"""Application settings.

Single source of configuration, loaded from environment / `.env`. The MVP runs
as one hardcoded dev tenant + user (no auth UI); ``tenant_id`` / ``user_id`` are
on every row so turning on multi-tenant auth later is a flip, not a migration.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VIRES_", extra="ignore")

    # Database — SQLite for MVP, swap to Postgres for multi-tenant.
    database_url: str = "sqlite:///./vires.db"

    # Embedding / search.
    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384
    fastembed_cache_dir: str = ".fastembed_cache"
    vector_store_path: str = "data/exercises.npz"
    rrf_k: int = 60
    # cosine >= this => advisory "did you mean?" on add-exercise (name+keywords
    # embeddings cluster name-variants ~0.8+, so this is a suggestion, not a
    # hard block; exact normalized-name matches are caught lexically first).
    dedup_threshold: float = 0.82
    search_limit: int = 25

    # Single-user MVP identity (schema-ready multitenancy).
    dev_tenant_id: str = "dev-tenant"
    dev_user_id: str = "dev-user"

    # CORS — the Vite dev server during local development.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Where the built React app lives (served as static in production).
    web_dist_dir: str = "web/dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
