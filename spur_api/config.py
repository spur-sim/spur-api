from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://spur:spur@localhost:5432/spur_api"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables or a
    `.env` file (see `.env.example`)."""

    model_config = SettingsConfigDict(env_prefix="SPUR_API_", env_file=".env")

    # Browser origins allowed to call the API from another origin, e.g.
    # ["https://app.example.com"]. Empty (the default) disables CORS
    # entirely; use ["*"] only for local experiments.
    cors_origins: list[str] = []

    auth_enabled: bool = False
    api_keys: list[str] = []

    database_url: str = DEFAULT_DATABASE_URL
    redis_url: str = DEFAULT_REDIS_URL

    # Chunks-per-run target used when a run request doesn't specify
    # chunk_size; see spur_api/worker/runner.py.
    default_chunk_count: int = 100
    # Fallback horizon (sim-time units) when a run request doesn't specify
    # `until` and the project's tours carry no deletion_time to derive one
    # from (e.g. an empty project).
    default_run_horizon: int = 86400


settings = Settings()
