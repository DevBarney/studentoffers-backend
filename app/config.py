import os

from pydantic_settings import BaseSettings, SettingsConfigDict

ON_VERCEL = os.getenv("VERCEL") == "1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    source_base: str = "https://www.studentoffers.co"
    database_path: str = "/tmp/offers.db" if ON_VERCEL else "data/offers.db"
    user_agent: str = "StudentOffersSync/1.0 (+local cache; respects 60 rpm public API)"
    request_timeout: float = 20.0 if ON_VERCEL else 45.0
    # Cold starts on Vercel should not block the first response on a full sync.
    sync_on_startup: bool = False if ON_VERCEL else True


settings = Settings()
