from __future__ import annotations

from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import uuid4

from nango.adapters.providers import ProviderCatalog, load_providers_yaml
from nango.api.models import (
    ActionTriggerRequest,
    ConnectSessionRecord,
    DeployValidationData,
    DeployValidationRequest,
    SyncTriggerRequest,
    TriggerConnectionInput,
)
from nango.contracts.connect import (
    ConnectSessionCreateRequest,
    ConnectSessionCreateResponse,
    ConnectSessionToken,
)
from nango.domain.errors import integration_not_found
from nango.domain.models import IntegrationConfig
from nango.domain.postgres_repositories import PostgresIntegrationConfigRepository
from nango.domain.repositories import (
    InMemoryIntegrationConfigRepository,
    IntegrationConfigRepository,
)
from nango.domain.services import DeployMetadataService, ProviderResolver
from nango.nango_yaml import ParserIssue, validate_nango_yaml_text
from nango.orchestrator import OrchestratorService
from nango.orchestrator.models import ImmediateTaskCreateRequest
from nango.utils.errors import ApplicationError

CONNECT_SESSION_TOKEN_PREFIX = "nango_connect_session_"
CONNECT_SESSION_TTL = timedelta(hours=1)

IntegrationRepository = IntegrationConfigRepository | PostgresIntegrationConfigRepository


class InMemoryConnectSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, ConnectSessionRecord] = {}

    def create(
        self,
        request: ConnectSessionCreateRequest,
        *,
        connect_base_url: str = "https://connect.nango.dev",
    ) -> ConnectSessionCreateResponse:
        token = f"{CONNECT_SESSION_TOKEN_PREFIX}{token_urlsafe(24)}"
        expires_at = datetime.now(UTC) + CONNECT_SESSION_TTL
        connect_link = f"{connect_base_url.rstrip('/')}/?session_token={token}"
        session = ConnectSessionRecord(
            token=token,
            expiresAt=expires_at,
            connectLink=connect_link,
            request=request,
        )
        self._sessions[token] = session
        return ConnectSessionCreateResponse(
            data=ConnectSessionToken(token=token, connect_link=connect_link, expires_at=expires_at)
        )

    def get(self, token: str) -> ConnectSessionRecord | None:
        session = self._sessions.get(token)
        if session is None or session.expires_at <= datetime.now(UTC):
            return None
        return session


class PublicAPIService:
    def __init__(
        self,
        *,
        providers: ProviderCatalog | None = None,
        integrations: IntegrationRepository | None = None,
        connect_sessions: InMemoryConnectSessionRepository | None = None,
        orchestrator: OrchestratorService | None = None,
    ) -> None:
        self._providers = providers
        self.integrations: IntegrationRepository = (
            integrations or InMemoryIntegrationConfigRepository()
        )
        self.connect_sessions = connect_sessions or InMemoryConnectSessionRepository()
        self.orchestrator = orchestrator or OrchestratorService()
        self.provider_resolver = ProviderResolver(providers)
        self.deploy_metadata = DeployMetadataService()

    def list_providers(self, *, language: str | None = None) -> list[dict[str, object]]:
        providers = (
            self._providers
            if self._providers is not None
            else load_providers_yaml(language=language)
        )
        return [
            {"provider": name, **provider}
            for name, provider in sorted(providers.items(), key=lambda item: item[0])
        ]

    def get_provider(self, provider_name: str) -> dict[str, object]:
        provider = self.provider_resolver.resolve(provider_name)
        return {"provider": provider_name, **provider}

    async def list_integrations(self, environment_id: int = 1) -> list[IntegrationConfig]:
        if isinstance(self.integrations, PostgresIntegrationConfigRepository):
            return list(await self.integrations.list_for_environment(environment_id))
        return list(self.integrations.list_for_environment(environment_id))

    async def get_integration(
        self,
        provider_config_key: str,
        environment_id: int = 1,
    ) -> IntegrationConfig:
        if isinstance(self.integrations, PostgresIntegrationConfigRepository):
            integration = await self.integrations.get_by_key(
                environment_id=environment_id,
                provider_config_key=provider_config_key,
            )
        else:
            integration = self.integrations.get_by_key(
                environment_id=environment_id,
                provider_config_key=provider_config_key,
            )
        if integration is None:
            raise integration_not_found(provider_config_key)
        return integration

    def validate_deploy(self, request: DeployValidationRequest) -> DeployValidationData:
        yaml_text = request.yaml or request.nango_yaml
        if not yaml_text:
            raise ApplicationError(
                "missing_nango_yaml",
                message='Request body must include "yaml" or "nangoYaml"',
                status_code=400,
            )

        result = validate_nango_yaml_text(yaml_text)
        metadata = (
            self.deploy_metadata.from_parsed_nango_yaml(result.parsed)
            if result.parsed
            else None
        )
        return DeployValidationData(
            valid=result.ok,
            metadata=metadata,
            errors=[_parser_issue_to_api_error(issue) for issue in result.errors],
            warnings=[_parser_issue_to_api_error(issue) for issue in result.warnings],
        )

    async def trigger_sync(self, request: SyncTriggerRequest) -> tuple[str, str]:
        connection = _resolve_connection(
            request.connection,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
            environment_id=request.environment_id,
        )
        task = await self.orchestrator.create_immediate(
            ImmediateTaskCreateRequest.model_validate(
                {
                    "name": f"sync:{connection.provider_config_key}:{request.sync_name}:{uuid4()}",
                    "ownerKey": connection.connection_id,
                    "group": {
                        "key": f"sync:{connection.provider_config_key}:{request.sync_name}",
                        "maxConcurrency": 1,
                    },
                    "retry": {"count": 0, "max": 0},
                    "timeoutSettingsInSecs": _default_timeouts(),
                    "args": {
                        "type": "sync",
                        "syncId": request.sync_id or request.sync_name,
                        "syncName": request.sync_name,
                        "syncVariant": request.sync_variant,
                        "debug": request.debug,
                        "connection": connection.model_dump(mode="json", by_alias=False),
                    },
                }
            )
        )
        return task.task_id, task.retry_key

    async def trigger_action(self, request: ActionTriggerRequest) -> tuple[str, str]:
        connection = _resolve_connection(
            request.connection,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
            environment_id=request.environment_id,
        )
        task = await self.orchestrator.create_immediate(
            ImmediateTaskCreateRequest.model_validate(
                {
                    "name": (
                        f"action:{connection.provider_config_key}:"
                        f"{request.action_name}:{uuid4()}"
                    ),
                    "ownerKey": connection.connection_id,
                    "group": {
                        "key": f"action:{connection.provider_config_key}:{request.action_name}",
                        "maxConcurrency": 1,
                    },
                    "retry": {"count": 0, "max": 0},
                    "timeoutSettingsInSecs": _default_timeouts(),
                    "args": {
                        "type": "action",
                        "actionName": request.action_name,
                        "activityLogId": request.activity_log_id or str(uuid4()),
                        "input": request.input,
                        "async": request.async_,
                        "connection": connection.model_dump(mode="json", by_alias=False),
                    },
                }
            )
        )
        return task.task_id, task.retry_key


def _resolve_connection(
    connection: TriggerConnectionInput | None,
    *,
    connection_id: str | None,
    provider_config_key: str | None,
    environment_id: int,
) -> TriggerConnectionInput:
    if connection is not None:
        return connection
    if not connection_id or not provider_config_key:
        raise ApplicationError(
            "missing_connection",
            message=(
                'Trigger requests require "connection" or both '
                '"connectionId" and "providerConfigKey"'
            ),
            status_code=400,
        )
    return TriggerConnectionInput(
        connectionId=connection_id,
        providerConfigKey=provider_config_key,
        environmentId=environment_id,
    )


def _default_timeouts() -> dict[str, int]:
    return {"createdToStarted": 30, "startedToCompleted": 300, "heartbeat": 30}


def _parser_issue_to_api_error(issue: ParserIssue) -> dict[str, object]:
    return {"code": issue.code, "message": issue.message, "path": list(issue.path)}
