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

    # AI coach (Anthropic). The key is hydrated onto the box from SSM at deploy
    # time (see infrastructure/deploy-on-merge.sh); absent => the coach endpoints
    # 503 and the rest of the app keeps working. Start on the cheapest model to
    # shake out bugs; bumping to claude-sonnet-4-6 is a one-line config flip.
    anthropic_api_key: str | None = None
    coach_model: str = "claude-haiku-4-5"
    coach_max_tokens: int = 4096
    # Optional explicit path to the coach system prompt. The tuned prompt is the
    # private edge (gitignored coach_system.txt, hydrated from SSM at deploy time);
    # absent => the committed coach_system.example.txt baseline is used.
    coach_prompt_path: str | None = None

    # Speech-to-text (optional). OpenAI-compatible Whisper endpoint — point
    # stt_base_url at Groq for a cheaper/faster Whisper. Key SSM-hydrated like the
    # others; absent => the /coach/transcribe endpoint 503s and the mic is hidden.
    stt_api_key: str | None = None
    stt_model: str = "whisper-1"
    stt_base_url: str = "https://api.openai.com/v1"

    # Web Push (optional) — locked-screen timer alerts. VAPID keypair: the public
    # key (base64url applicationServerKey) is served to the browser; the private
    # key (PEM) signs pushes. SSM-hydrated; absent => /push endpoints 503 and the
    # client falls back to foreground beep/wake-lock only.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:brian@nousergon.ai"

    # CORS — the Vite dev server during local development.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Where the built React app lives (served as static in production).
    web_dist_dir: str = "web/dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
