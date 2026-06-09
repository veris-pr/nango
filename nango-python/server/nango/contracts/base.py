from typing import Any

from pydantic import BaseModel, ConfigDict

type JsonObject = dict[str, Any]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)
