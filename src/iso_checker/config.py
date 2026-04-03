from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ISO_CHECKER_", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8583
    scenario_file: Path = Path("scenarios/default.yaml")
    scenario_name: str | None = None
    log_level: str = "INFO"
    report_path: Path | None = None
    json_stdout: bool = False
    max_scenario_repeats: int = Field(default=1, ge=1, description="Restart scenario after completion")


def load_settings(**overrides: object) -> Settings:
    return Settings(**{k: v for k, v in overrides.items() if v is not None})
