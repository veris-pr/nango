"""Provider catalog value object.

A read-only view of a single entry from ``packages/providers/providers.yaml``.
Only the fields needed by the integration-read boundary are modeled.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    display_name: str
    auth_mode: str
    #: When present, the provider supports incoming webhooks and the
    #: integration-read response populates ``webhook_url``.
    webhook_routing_script: str | None = None