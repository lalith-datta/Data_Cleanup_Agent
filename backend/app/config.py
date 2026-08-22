"""Central env config — every environment-specific value lives here.

Local-first, cloud-ready: adopting Supabase / Vercel / Render later is a
matter of changing these env vars, not code (see docs/PRD.md §5).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database — SQLite locally, Supabase Postgres later via this one var.
    database_url: str = "sqlite:///./migration.db"

    # LLM (provider-agnostic via LangChain). Empty provider -> MockLLM.
    llm_provider: str = ""
    llm_model: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Storage — local dir now, Supabase Storage later behind the adapter.
    upload_dir: str = "./uploads"

    # Target schema — the canonical employee spec (repo-relative).
    target_schema_path: str = "../data/target_schema.yaml"

    # Escalation boundary tuning (defensible, config-driven — PRD §8).
    auto_apply_threshold: float = 0.90
    min_map_threshold: float = 0.70
    ambiguous_delta: float = 0.08
    max_push_attempts: int = 3

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
