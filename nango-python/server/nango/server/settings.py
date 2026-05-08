from os import environ
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

CutoverMode = Literal["disabled", "shadow", "canary", "active"]


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    service_name: str = Field(default="nango-python-core", min_length=1)
    environment: str = Field(default="development", min_length=1)
    database_url: str | None = None
    redis_url: str | None = None
    cutover_mode: CutoverMode = "disabled"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            service_name=environ.get("NANGO_PYTHON_SERVICE_NAME", "nango-python-core"),
            environment=environ.get("NANGO_ENV", "development"),
            database_url=environ.get("DATABASE_URL"),
            redis_url=environ.get("REDIS_URL"),
            cutover_mode=cast(
                CutoverMode,
                environ.get("NANGO_PYTHON_CUTOVER_MODE", "disabled"),
            ),
        )
