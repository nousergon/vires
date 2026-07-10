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
    # Separate name-only embedding index for the add-exercise dedup hint. Kept
    # apart from the search index above (name+keywords) because that diluted
    # signal clustered any shared word ~0.8+ and produced confident false
    # positives (e.g. "lunge dumbbell overhead" -> "Incline Dumbbell Flyes" @
    # 0.85); a name-only index is the higher-precision signal the hint needs.
    name_vector_store_path: str = "data/exercise_names.npz"
    rrf_k: int = 60
    # cosine >= this => non-blocking "similar exercise" hint alongside a
    # successful create (never gates the create itself; exact normalized-name
    # matches are caught lexically first, above, and remain a hard block).
    dedup_hint_threshold: float = 0.90
    search_limit: int = 25

    # Single-user MVP identity (schema-ready multitenancy).
    dev_tenant_id: str = "dev-tenant"
    dev_user_id: str = "dev-user"

    # AI coach — provider-agnostic via the krepis adapter. WHICH model runs is
    # operator config, resolved (in order): VIRES_COACH_LLM env override →
    # /vires/llm/coach SSM parameter (60s TTL — flip providers live, no
    # redeploy; e.g. "openrouter:moonshotai/kimi-k2.6") → the code default
    # below (anthropic + coach_model). Keys are hydrated onto the box from SSM
    # at deploy time (see infrastructure/deploy-on-merge.sh); a missing key
    # for the ACTIVE provider => the coach endpoints 503 and the rest of the
    # app keeps working.
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    coach_llm_ssm_param: str = "/vires/llm/coach"
    coach_model: str = "claude-haiku-4-5"
    coach_max_tokens: int = 4096
    # Coach telemetry sinks (parents auto-created). Cost rows append on every
    # generation (krepis record_llm_call — provider/tokens/cost_source); SFT
    # distillation rows append only when LLM_SFT_CAPTURE_ENABLED=1.
    coach_cost_log_path: str = "data/coach_cost.jsonl"
    coach_sft_sink_path: str = "data/sft/coach.jsonl"
    # Optional explicit path to the coach system prompt. The tuned prompt is the
    # private edge (gitignored coach_system.txt, hydrated from SSM at deploy time);
    # absent => the committed coach_system.example.txt baseline is used.
    coach_prompt_path: str | None = None
    # Kill-switch for deterministic post-workout autoregulation (the micro loop
    # that nudges upcoming planned loads from logged performance). Default on.
    autoregulation_enabled: bool = True

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

    # Auth (vires-ops#49) — magic-link login + DB-backed sessions.
    # Email delivery (Resend). Key SSM-hydrated like the others; absent =>
    # magic-link requests fail loud in production, but in `env=="development"`
    # the link is logged instead of sent (see api.services.email) so local
    # dev never needs a live inbox.
    resend_api_key: str | None = None
    email_sender: str = "no-reply@nousergon.ai"
    env: str = "production"
    # Where the magic-link email points — the SPA's own origin.
    frontend_url: str = "https://vires.nousergon.ai"
    magic_link_ttl_seconds: int = 300
    magic_link_rate_limit_per_email: int = 5
    magic_link_rate_limit_window_seconds: int = 60
    session_ttl_seconds: int = 60 * 60 * 24 * 7  # 7 days
    # A session touched less recently than "now - this" gets its expiry
    # pushed out another `session_ttl_seconds` (rolling refresh).
    session_refresh_threshold_seconds: int = 60 * 60 * 24  # 1 day
    # Kill-switch: require the signup email to be on the allowlist for any
    # signup beyond the very first (bootstrap) user. Flip to False to open
    # signup wide.
    allowlist_required: bool = True
    # Local-dev-only escape hatch: skip real session verification entirely
    # and resolve the hardcoded dev identity, exactly like before auth
    # existed. Must NEVER be true in a deployed .env — nothing in the
    # deploy pipeline sets it, and it's not SSM-hydrated.
    dev_auth_bypass: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
