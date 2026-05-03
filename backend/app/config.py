from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./agenteval.db", validation_alias="AGENTEVAL_DATABASE_URL")
    claude_model: str = Field(
        default="claude-3-5-sonnet-latest",
        validation_alias=AliasChoices("CLAUDE_MODEL", "ANTHROPIC_MODEL"),
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    api_title: str = "AgentEval Harness API"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
