from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime limits kept in one place so the agent is easy to tune."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    max_file_size_mb: int = 5
    max_rows: int = 10_000
    max_cols: int = 100
    min_rows: int = 1
    max_user_text_chars: int = 2_000
    max_retries: int = 3
    retry_base_delay: float = 1.0
    llm_timeout_seconds: float = 20.0
    max_context_tokens: int = 6_000
    max_output_tokens: int = 1_500
    execution_timeout_seconds: int = 20
    max_plan_attempts: int = 2
    memory_turn_limit: int = 12
    log_dir: Path = Path("logs")
    memory_db_path: Path = Path(".agent_state/memory.sqlite3")


settings = Settings()
