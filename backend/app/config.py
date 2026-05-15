from functools import lru_cache
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(default="sqlite:///./agenteval.db", validation_alias="AGENTEVAL_DATABASE_URL")
    claude_model: str = Field(
        default="claude-sonnet-4-20250514",
        validation_alias=AliasChoices("CLAUDE_MODEL", "ANTHROPIC_MODEL"),
    )
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    google_model: str = Field(default="gemini-2.5-flash", validation_alias=AliasChoices("GOOGLE_MODEL", "GEMINI_MODEL"))
    openrouter_model: str = Field(default="meta-llama/llama-3.3-70b-instruct", validation_alias="OPENROUTER_MODEL")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    api_title: str = "AgentEval Harness API"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
