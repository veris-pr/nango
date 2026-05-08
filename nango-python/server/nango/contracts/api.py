from typing import Literal

from nango.contracts.base import ContractModel


class HealthResponse(ContractModel):
    status: Literal["ok"]
    service: str
    cutover_mode: Literal["disabled", "shadow", "canary", "active"] = "disabled"
