from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

Action = Literal["create", "read", "update", "delete", "*"]
Resource = Literal[
    "team",
    "team_member",
    "invite",
    "connect_ui_settings",
    "billing",
    "plan",
    "environment",
    "environment_production_flag",
    "environment_key",
    "environment_variable",
    "webhook",
    "integration",
    "connection",
    "flow",
    "sync_command",
    "secret_key",
    "connection_credential",
    "log",
    "*",
]
Scope = Literal["production", "non-production", "global"]


@dataclass(frozen=True, slots=True)
class Permission:
    action: Action
    resource: Resource
    scope: Scope

    def as_string(self) -> str:
        return f"{self.action}:{self.resource}:{self.scope}"


PERMISSIONS: Mapping[str, Permission] = MappingProxyType(
    {
        "canManageTeam": Permission("update", "team", "global"),
        "canUpdateTeamMember": Permission("update", "team_member", "global"),
        "canRemoveTeamMember": Permission("delete", "team_member", "global"),
        "canInviteMember": Permission("create", "invite", "global"),
        "canCancelInvitation": Permission("delete", "invite", "global"),
        "canManageConnectUI": Permission("update", "connect_ui_settings", "global"),
        "canManageBilling": Permission("*", "billing", "global"),
        "canChangePlan": Permission("update", "plan", "global"),
        "canToggleIsProduction": Permission(
            "update", "environment_production_flag", "global"
        ),
        "canCreateEnvironment": Permission("create", "environment", "global"),
        "canAccessProdEnvironment": Permission("read", "environment", "production"),
        "canWriteProdIntegrations": Permission("update", "integration", "production"),
        "canDeleteProdIntegrations": Permission("delete", "integration", "production"),
        "canWriteProdConnections": Permission("update", "connection", "production"),
        "canDeleteProdConnections": Permission("delete", "connection", "production"),
        "canWriteProdFlows": Permission("update", "flow", "production"),
        "canWriteProdEnvironment": Permission("update", "environment", "production"),
        "canWriteProdEnvironmentKeys": Permission(
            "update", "environment_key", "production"
        ),
        "canWriteProdEnvironmentVariables": Permission(
            "update", "environment_variable", "production"
        ),
        "canWriteProdWebhooks": Permission("update", "webhook", "production"),
        "canDeleteProdEnvironment": Permission("delete", "environment", "production"),
        "canReadProdSecretKey": Permission("read", "secret_key", "production"),
        "canReadProdConnectionCredentials": Permission(
            "read", "connection_credential", "production"
        ),
        "canUseProdPlayground": Permission("update", "sync_command", "production"),
    }
)

permissions = PERMISSIONS

__all__ = ["Action", "PERMISSIONS", "Permission", "Resource", "Scope", "permissions"]
