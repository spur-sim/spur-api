from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via environment variables or a
    `.env` file (see `.env.example`).

    Phase 1 only uses `api_keys`/`auth_enabled` — `database_url`/`redis_url`
    are declared now so later phases can read them without touching this
    module's shape again, but nothing consumes them yet.
    """

    model_config = SettingsConfigDict(env_prefix="SPUR_API_", env_file=".env")

    auth_enabled: bool = False
    api_keys: list[str] = []

    database_url: str | None = None
    redis_url: str | None = None


settings = Settings()
