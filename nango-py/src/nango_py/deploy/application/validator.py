"""Deploy validation use case.

Parses nango.yaml text and returns metadata (flows, models, errors, warnings).
Mirrors the spike's ``validate_deploy`` and the TS ``postDeploy`` validation path.

The full TS deploy also reconciles differences, persists sync configs, and
starts/stops syncs via the orchestrator. This use case covers validation +
metadata extraction; reconciliation and persistence are added in the full
deploy path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nango_py.deploy.domain.errors import MissingNangoYaml
from nango_py.nango_yaml import (
    ParsedNangoYaml,
    validate_nango_yaml_text,
)

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class DeployValidationResult:
    valid: bool
    metadata: JsonObject | None
    errors: list[JsonObject]
    warnings: list[JsonObject]


class DeployValidator:
    """Validates nango.yaml text and extracts deploy metadata."""

    def validate(self, yaml_text: str | None) -> DeployValidationResult:
        if not yaml_text:
            raise MissingNangoYaml()

        result = validate_nango_yaml_text(yaml_text)
        metadata = self._metadata_from_parsed(result.parsed) if result.parsed else None
        return DeployValidationResult(
            valid=result.ok,
            metadata=metadata,
            errors=[_issue_to_dict(issue) for issue in result.errors],
            warnings=[_issue_to_dict(issue) for issue in result.warnings],
        )

    @staticmethod
    def _metadata_from_parsed(parsed: ParsedNangoYaml) -> JsonObject:
        flows: list[JsonObject] = []
        for integration in parsed.integrations:
            for sync in integration.syncs:
                flows.append({
                    "providerConfigKey": integration.provider_config_key,
                    "name": sync.name,
                    "type": "sync",
                    "models": list(sync.output),
                    "runs": sync.runs,
                    "autoStart": sync.auto_start,
                    "syncType": sync.sync_type,
                    "trackDeletes": sync.track_deletes,
                    "webhookSubscriptions": list(sync.webhook_subscriptions),
                    "scopes": list(sync.scopes),
                    "endpoints": [
                        {"method": ep.method, "path": ep.path, "group": ep.group}
                        for ep in sync.endpoints
                    ],
                })
            for action in integration.actions:
                endpoints: list[JsonObject] = []
                if action.endpoint is not None:
                    endpoints.append({
                        "method": action.endpoint.method,
                        "path": action.endpoint.path,
                        "group": action.endpoint.group,
                    })
                flows.append({
                    "providerConfigKey": integration.provider_config_key,
                    "name": action.name,
                    "type": "action",
                    "models": list(action.output or ()),
                    "input": action.input,
                    "scopes": list(action.scopes),
                    "endpoints": endpoints,
                })
        return {
            "flows": flows,
            "modelNames": list(parsed.models),
        }


def _issue_to_dict(issue: Any) -> JsonObject:
    return {"code": issue.code, "message": issue.message, "path": list(issue.path)}