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
    # Role skill models (docs/superpowers/specs/2026-10-06-skill-models-design.md): built
    # packages, and harvested learning candidates. Both stay on the node, never in git.
    MIA_MODELS_DIR: Path = Field(default=Path("data/models"))
    MIA_LEARNING_DIR: Path = Field(default=Path("data/learning"))
    # Photos and files people send as proof of work (visit.proof_refs point into it).
    MIA_MEDIA_DIR: Path = Field(default=Path("data/media"))
    MIA_EGRESS_LEVEL: EgressLevel = "pseudonymised"
    # Who picks the shift supervisor's tool: the Pydantic AI agent, or Jev (spec 2026-10-17-jev-decider;
    # synthetic and demo data only under D18).
    MIA_DECIDER: Literal["agent", "jev"] = "agent"
    MIA_TYPESAFE_URL: str = "https://api.typesafe.ai/v1/systemone"
    MIA_TYPESAFE_KEY: str = ""
    MIA_JEV_MODEL: str = "jev-1.13.0"  # pinned, so measurements compare
    # Who hears about Jev outages (spec 2026-10-18); empty: the log only.
    MIA_DEVELOPER_PERSON_ID: str = ""
    MIA_ORG: str = "demo"
    MIA_TICK_SECONDS: int = 30
    MIA_GEOCODER: str = "digitransit"
    MIA_GEOCODER_KEY: str = ""
    MIA_GEOCODER_URL: str = "https://api.digitransit.fi/geocoding/v1"
    # Channels (ADR 007). MIA_NODE_SECRET keys link-code HMACs; MIA_PUBLIC_URL builds app links.
    MIA_NODE_SECRET: str = ""
    MIA_PUBLIC_URL: str = "http://localhost:8000"
    # Authentication (ADR 011). The master key file (mia keys init) derives every subkey;
    # without it MIA_NODE_SECRET is the key, so invites made before it keep working.
    MIA_MASTER_KEY_FILE: Path | None = None
    MIA_AUTH_MODE: Literal["required", "dev"] = "required"
    # The sim channel's webhook secret (dev mode only, ADR 021); empty keeps the public default.
    MIA_SIM_SECRET: str = ""
    # Peers allowed to set CF-Connecting-IP (the cloudflared container), comma separated.
    MIA_TRUSTED_PROXIES: str = ""
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
