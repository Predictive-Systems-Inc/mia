"""Node settings, read from the environment and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

NODE_DIR = Path(__file__).resolve().parent.parent
EgressLevel = Literal["none", "pseudonymised"]


class Settings(BaseSettings):
    """Settings for one Mia Node. Field names match the MIA_* environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    MIA_DB_PATH: Path = Field(default=Path("data/mia.db"))
    MIA_MODEL: str = "test"
    MIA_GATEWAY_URL: str = "http://localhost:4000/v1"
    MIA_GATEWAY_KEY: str = ""
    # OpenAI-compatible server on this machine or network (Ollama) for MIA_MODEL=local/<model>.
    MIA_LOCAL_URL: str = "http://localhost:11434/v1"
    # Thinking (reasoning) on local models: off by default because it makes every turn slow on
    # small hardware; turn on when the evals show it helps a given model.
    MIA_LOCAL_THINKING: bool = False
    MIA_EGRESS_LEVEL: EgressLevel = "pseudonymised"
    MIA_ORG: str = "demo"
    MIA_TICK_SECONDS: int = 30
    MIA_GEOCODER: str = "digitransit"
    MIA_GEOCODER_KEY: str = ""
    MIA_GEOCODER_URL: str = "https://api.digitransit.fi/geocoding/v1"
    # Channels (ADR 007). MIA_NODE_SECRET keys link-code HMACs; MIA_PUBLIC_URL builds app links.
    MIA_NODE_SECRET: str = ""
    MIA_PUBLIC_URL: str = "http://localhost:8000"
    MIA_WA_TOKEN: str = ""
    MIA_WA_APP_SECRET: str = ""
    MIA_WA_VERIFY_TOKEN: str = ""
    MIA_WA_PHONE_NUMBER_ID: str = ""
    MIA_WA_NUMBER: str = ""
    MIA_WA_GRAPH_URL: str = "https://graph.facebook.com/v26.0"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.MIA_DB_PATH}"

    @property
    def config_dir(self) -> Path:
        return NODE_DIR / "config"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings (cached; tests call get_settings.cache_clear())."""
    return Settings()
