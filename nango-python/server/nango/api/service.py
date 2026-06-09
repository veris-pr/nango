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
    PublicConnection,
    PublicConnectionEndUser,
    PublicConnectionEndUserOrganization,
    PublicConnectionError,
    PublicConnectionFull,
    SyncTriggerRequest,
    TriggerConnectionInput,
)
from nango.auth.models import AccountContext
from nango.contracts.connect import (
    ConnectSessionCreateRequest,
    ConnectSessionCreateResponse,
    ConnectSessionToken,
)
from nango.domain.errors import integration_not_found
from nango.domain.models import Connection, IntegrationConfig
from nango.domain.postgres_repositories import (
    PostgresConnectionRepository,
    PostgresIntegrationConfigRepository,
    PostgresSyncRepository,
)
from nango.domain.repositories import (
    ConnectionRepository,
    InMemoryConnectionRepository,
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
ConnectionReadRepository = ConnectionRepository | PostgresConnectionRepository
SyncReadRepository = PostgresSyncRepository | None


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
        connections: ConnectionReadRepository | None = None,
        syncs: SyncReadRepository = None,
        connect_sessions: InMemoryConnectSessionRepository | None = None,
        orchestrator: OrchestratorService | None = None,
    ) -> None:
        self._providers = providers
        self.integrations: IntegrationRepository = (
            integrations or InMemoryIntegrationConfigRepository()
        )
        self.connections: ConnectionReadRepository = connections or InMemoryConnectionRepository()
        self.syncs = syncs
        self.connect_sessions = connect_sessions or InMemoryConnectSessionRepository()
        self.orchestrator = orchestrator or OrchestratorService()
        self.provider_resolver = ProviderResolver(providers)
        self.deploy_metadata = DeployMetadataService()

    async def _lookup_integration(
        self,
        *,
        provider_config_key: str,
        environment_id: int,
    ) -> IntegrationConfig | None:
        if isinstance(self.integrations, PostgresIntegrationConfigRepository):
            return await self.integrations.get_by_key(
                environment_id=environment_id,
                provider_config_key=provider_config_key,
            )
        return self.integrations.get_by_key(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
        )

    async def _lookup_connection(
        self,
        *,
        environment_id: int,
        provider_config_key: str,
        connection_id: str,
    ) -> Connection | None:
        if isinstance(self.connections, PostgresConnectionRepository):
            return await self.connections.get_by_id(
                environment_id=environment_id,
                provider_config_key=provider_config_key,
                connection_id=connection_id,
            )
        return self.connections.get_by_id(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            connection_id=connection_id,
        )

    async def _list_connections(
        self,
        *,
        environment_id: int,
        connection_id: str | None,
        provider_config_keys: tuple[str, ...],
        search: str | None,
        end_user_id: str | None,
        end_user_organization_id: str | None,
        tags: dict[str, str] | None,
        limit: int,
        page: int,
    ) -> tuple[Connection, ...]:
        if isinstance(self.connections, PostgresConnectionRepository):
            return await self.connections.list_for_environment(
                environment_id,
                connection_id=connection_id,
                provider_config_keys=provider_config_keys,
                search=search,
                end_user_id=end_user_id,
                end_user_organization_id=end_user_organization_id,
                tags=tags,
                limit=limit,
                page=page,
            )
        return self.connections.list_for_environment(
            environment_id,
            connection_id=connection_id,
            provider_config_keys=provider_config_keys,
            search=search,
            end_user_id=end_user_id,
            end_user_organization_id=end_user_organization_id,
            tags=tags,
            limit=limit,
            page=page,
        )

    async def _providers_by_connection_key(
        self,
        *,
        environment_id: int,
        provider_config_keys: tuple[str, ...],
    ) -> dict[str, str]:
        providers_by_key: dict[str, str] = {}
        for provider_config_key in provider_config_keys:
            integration = await self._lookup_integration(
                provider_config_key=provider_config_key,
                environment_id=environment_id,
            )
            if integration is not None:
                providers_by_key[integration.provider_config_key] = integration.provider
        return providers_by_key

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

    async def list_public_connections(
        self,
        *,
        auth: AccountContext,
        connection_id: str | None = None,
        integration_id: str | None = None,
        search: str | None = None,
        end_user_id: str | None = None,
        end_user_organization_id: str | None = None,
        tags: dict[str, str] | None = None,
        limit: int = 10_000,
        page: int = 0,
    ) -> list[PublicConnection]:
        provider_config_keys = (
            tuple(part.strip() for part in integration_id.split(",") if part.strip())
            if integration_id
            else ()
        )
        connections = await self._list_connections(
            environment_id=auth.environment.id,
            connection_id=connection_id,
            provider_config_keys=provider_config_keys,
            search=search,
            end_user_id=end_user_id,
            end_user_organization_id=end_user_organization_id,
            tags=tags,
            limit=limit,
            page=page,
        )
        providers_by_key = await self._providers_by_connection_key(
            environment_id=auth.environment.id,
            provider_config_keys=tuple(
                sorted({connection.provider_config_key for connection in connections})
            ),
        )
        return [
            PublicConnection(
                id=connection.id,
                connection_id=connection.connection_id,
                provider_config_key=connection.provider_config_key,
                created=connection.created_at,
                metadata=connection.metadata,
                provider=providers_by_key[connection.provider_config_key],
                errors=_public_connection_errors(connection),
                end_user=_public_connection_end_user(connection),
                tags=connection.tags,
            )
            for connection in connections
            if connection.provider_config_key in providers_by_key
        ]

    async def list_integrations(self, environment_id: int = 1) -> list[IntegrationConfig]:
        if isinstance(self.integrations, PostgresIntegrationConfigRepository):
            return list(await self.integrations.list_for_environment(environment_id))
        return list(self.integrations.list_for_environment(environment_id))

    async def get_integration(
        self,
        provider_config_key: str,
        environment_id: int = 1,
    ) -> IntegrationConfig:
        integration = await self._lookup_integration(
            provider_config_key=provider_config_key,
            environment_id=environment_id,
        )
        if integration is None:
            raise integration_not_found(provider_config_key)
        return integration

    async def get_public_connection(
        self,
        *,
        connection_id: str,
        provider_config_key: str,
        auth: AccountContext,
    ) -> PublicConnectionFull:
        integration = await self._lookup_integration(
            provider_config_key=provider_config_key,
            environment_id=auth.environment.id,
        )
        if integration is None:
            raise ApplicationError(
                "unknown_provider_config",
                message="Provider does not exist",
                status_code=400,
            )

        connection = await self._lookup_connection(
            environment_id=auth.environment.id,
            provider_config_key=provider_config_key,
            connection_id=connection_id,
        )
        if connection is None:
            raise ApplicationError(
                "connection_not_found",
                message=f'Connection "{connection_id}" was not found',
                status_code=404,
            )

        include_credentials = auth.auth_source != "customer_key" or (
            "environment:connections:read_credentials" in auth.scopes
        )
        return PublicConnectionFull(
            id=connection.id,
            connection_id=connection.connection_id,
            provider_config_key=connection.provider_config_key,
            provider=integration.provider,
            errors=_public_connection_errors(connection),
            end_user=_public_connection_end_user(connection),
            tags=connection.tags,
            metadata=connection.metadata,
            connection_config=connection.connection_config,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
            last_fetched_at=connection.last_fetched_at,
            credentials=connection.credentials if include_credentials else {},
        )

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
        connection = await self._trigger_connection(
            request.connection,
            connection_id=request.connection_id,
            provider_config_key=request.provider_config_key,
            environment_id=request.environment_id,
        )
        sync_id = request.sync_id or request.sync_name
        if self.syncs is not None:
            resolved_sync = await self.syncs.get_by_name(
                connection_id=connection.id,
                name=request.sync_name,
                variant=request.sync_variant,
            )
            if resolved_sync is None:
                raise ApplicationError(
                    "no_syncs_found",
                    message="No syncs found given the inputs.",
                    status_code=400,
                )
            sync_id = resolved_sync.id
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
                        "syncId": sync_id,
                        "syncName": request.sync_name,
                        "syncVariant": request.sync_variant,
                        "debug": request.debug,
                        "connection": connection.model_dump(mode="json", by_alias=False),
                    },
                }
            )
        )
        return task.task_id, task.retry_key

    async def trigger_syncs(self, requests: list[SyncTriggerRequest]) -> None:
        for request in requests:
            await self.trigger_sync(request)

    async def trigger_action(self, request: ActionTriggerRequest) -> tuple[str, str]:
        connection = await self._trigger_connection(
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
                    "retry": {"count": 0, "max": request.retry_max},
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

    async def _trigger_connection(
        self,
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

        resolved_connection = await self._lookup_connection(
            environment_id=environment_id,
            provider_config_key=provider_config_key,
            connection_id=connection_id,
        )
        if resolved_connection is None:
            raise ApplicationError(
                "connection_not_found",
                message=f'Connection "{connection_id}" was not found',
                status_code=404,
            )

        return TriggerConnectionInput(
            id=resolved_connection.id,
            connectionId=resolved_connection.connection_id,
            providerConfigKey=resolved_connection.provider_config_key,
            environmentId=resolved_connection.environment_id,
        )


def _default_timeouts() -> dict[str, int]:
    return {"createdToStarted": 30, "startedToCompleted": 300, "heartbeat": 30}


def _parser_issue_to_api_error(issue: ParserIssue) -> dict[str, object]:
    return {"code": issue.code, "message": issue.message, "path": list(issue.path)}


def _public_connection_errors(connection: Connection) -> list[PublicConnectionError]:
    return [PublicConnectionError(**active_log) for active_log in connection.active_logs]


def _public_connection_end_user(connection: Connection) -> PublicConnectionEndUser | None:
    end_user = connection.end_user
    if end_user is None:
        return None
    end_user_id = end_user.get("end_user_id")
    if not isinstance(end_user_id, str):
        return None

    organization_id = end_user.get("organization_id")
    organization: PublicConnectionEndUserOrganization | None = None
    if isinstance(organization_id, str):
        organization = PublicConnectionEndUserOrganization(
            id=organization_id,
            display_name=_optional_str_value(end_user.get("organization_display_name")),
        )

    return PublicConnectionEndUser(
        id=end_user_id,
        display_name=_optional_str_value(end_user.get("display_name")),
        email=_optional_str_value(end_user.get("email")),
        tags=_optional_string_dict(end_user.get("tags")),
        organization=organization,
    )


def _optional_str_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_string_dict(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items() if isinstance(item, str)}
