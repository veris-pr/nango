"""Composition root for the read boundaries.

Wires the auth gateway, integration repository, provider catalog, connection
repository, and use cases into a FastAPI app. Transport errors are mapped to the
TypeScript error envelope via the :class:`ApiError` exception handler.

Defaults mirror the TypeScript env resolution:
- ``base_public_url`` = ``NANGO_PUBLIC_SERVER_URL`` || ``NANGO_SERVER_URL`` || ``http://localhost:3003``
- ``webhook_receive_url`` = ``NANGO_SERVER_URL`` + ``/webhook``
- ``providers_path`` = the repo's ``packages/providers/providers.yaml``
"""

from __future__ import annotations

from os import environ
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango_py.auth.infrastructure.sqlalchemy_auth_gateway import SqlAlchemyAuthGateway
from nango_py.auth_flows.application.create_auth_connection import CreateAuthConnection
from nango_py.auth_flows.transport.routes import create_auth_flows_router
from nango_py.connect_sessions.application.use_cases import (
    CreateConnectSession,
    DeleteConnectSession,
    GetConnectSessionByToken,
)
from nango_py.connect_sessions.infrastructure.sqlalchemy_connect_session_repository import (
    SqlAlchemyConnectSessionRepository,
)
from nango_py.connect_sessions.transport.routes import create_connect_sessions_router
from nango_py.connections.application.credential_refresher import CredentialRefresher
from nango_py.connections.application.crud import ConnectionCrudService
from nango_py.connections.application.get_connection import GetConnection
from nango_py.connections.application.list_connections import ListConnections
from nango_py.connections.infrastructure.sqlalchemy_connection_repository import (
    SqlAlchemyConnectionRepository,
)
from nango_py.connections.transport.routes import create_connections_router
from nango_py.deploy.transport.routes import create_deploy_router
from nango_py.integrations.application.crud import IntegrationCrudService
from nango_py.integrations.application.get_integration import GetIntegration
from nango_py.integrations.application.list_integrations import ListIntegrations
from nango_py.integrations.infrastructure.provider_catalog import (
    DEFAULT_PROVIDERS_PATH,
    YamlProviderCatalog,
)
from nango_py.integrations.infrastructure.sqlalchemy_integration_repository import (
    SqlAlchemyIntegrationRepository,
)
from nango_py.integrations.transport.routes import create_integrations_router
from nango_py.jobs.application.processor import JobsProcessorService
from nango_py.jobs.domain.runner_boundary import NodeRunnerClient
from nango_py.jobs.transport.routes import create_jobs_callback_router
from nango_py.keystore.infrastructure.sqlalchemy_private_key_repository import (
    SqlAlchemyPrivateKeyRepository,
)
from nango_py.misc.transport.routes import (
    create_mcp_router,
    create_misc_router,
    create_remote_function_router,
    create_v1_passthrough_router,
)
from nango_py.proxy.application.proxy_request import ProxyRequest
from nango_py.proxy.transport.routes import create_proxy_router
from nango_py.public_records.transport.routes import create_public_records_router
from nango_py.records.infrastructure.postgres_records_repository import (
    PostgresRecordsRepository,
)
from nango_py.records.transport.routes import create_persist_router
from nango_py.scheduler.application.orchestrator_service import OrchestratorService
from nango_py.scheduler.infrastructure.postgres_scheduler_repository import (
    PostgresSchedulerRepository,
)
from nango_py.scheduler.transport.routes import create_orchestrator_router
from nango_py.shared.errors import ApiError
from nango_py.sync_control.transport.routes import create_sync_control_router
from nango_py.webhooks.transport.routes import create_webhook_router

DEFAULT_BASE_PUBLIC_URL = "http://localhost:3003"


class _RunnerTransport:
    async def call(self, operation: str, payload: object) -> object:
        raise NotImplementedError(
            "runner transport not configured — set app.state.runner_transport"
        )


def create_app(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    encryption_key: str,
    providers_path: str | Path | None = None,
    base_public_url: str | None = None,
    webhook_receive_url: str | None = None,
    httpx_transport: Any = None,
) -> FastAPI:
    resolved_base = (
        base_public_url
        or environ.get("NANGO_PUBLIC_SERVER_URL")
        or environ.get("NANGO_SERVER_URL")
        or DEFAULT_BASE_PUBLIC_URL
    )
    resolved_webhook = webhook_receive_url or (
        environ.get("NANGO_SERVER_URL", DEFAULT_BASE_PUBLIC_URL).rstrip("/") + "/webhook"
    )
    resolved_providers = providers_path or DEFAULT_PROVIDERS_PATH

    auth_gateway = SqlAlchemyAuthGateway(session_factory, encryption_key=encryption_key)
    integration_repo = SqlAlchemyIntegrationRepository(
        session_factory, encryption_key=encryption_key
    )
    connection_repo = SqlAlchemyConnectionRepository(
        session_factory, encryption_key=encryption_key
    )
    provider_catalog = YamlProviderCatalog.from_path(resolved_providers)
    connection_crud = ConnectionCrudService(
        session_factory=session_factory,
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
        encryption_key=encryption_key,
    )
    provider_catalog = YamlProviderCatalog.from_path(resolved_providers)

    get_integration = GetIntegration(
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
        base_public_url=resolved_base,
        webhook_receive_url=resolved_webhook,
    )
    integration_crud = IntegrationCrudService(
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
        get_integration=get_integration,
    )
    list_integrations = ListIntegrations(
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
        base_public_url=resolved_base,
    )
    list_connections = ListConnections(connection_repository=connection_repo)
    get_connection = GetConnection(
        connection_repository=connection_repo,
        integration_repository=integration_repo,
    )
    records_repository = PostgresRecordsRepository(session_factory)
    scheduler_repository = PostgresSchedulerRepository(session_factory)
    orchestrator_service = OrchestratorService(scheduler_repository)
    _runner_transport = _RunnerTransport()
    _runner_client = NodeRunnerClient(_runner_transport)
    jobs_processor = JobsProcessorService(
        orchestrator=orchestrator_service,
        runner=_runner_client,
    )
    credential_refresher = CredentialRefresher(
        connection_repository=connection_repo,
        provider_catalog=provider_catalog,
    )
    proxy_request = ProxyRequest(
        connection_repository=connection_repo,
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
        credential_refresher=credential_refresher,
    )
    private_key_repo = SqlAlchemyPrivateKeyRepository(
        session_factory, encryption_key=encryption_key
    )
    connect_session_repo = SqlAlchemyConnectSessionRepository(session_factory)
    create_connect_session = CreateConnectSession(
        session_repository=connect_session_repo,
        private_key_repository=private_key_repo,
    )
    get_connect_session = GetConnectSessionByToken(
        session_repository=connect_session_repo,
        private_key_repository=private_key_repo,
    )
    delete_connect_session = DeleteConnectSession(
        session_repository=connect_session_repo,
        private_key_repository=private_key_repo,
    )
    create_auth_connection = CreateAuthConnection(
        connection_repository=connection_repo,
        integration_repository=integration_repo,
        provider_catalog=provider_catalog,
    )

    app = FastAPI(title="nango-py")
    app.state.auth_gateway = auth_gateway
    app.state.private_key_repo = private_key_repo
    app.state.connect_session_repo = connect_session_repo
    app.state.httpx_transport = httpx_transport

    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.to_envelope(), status_code=exc.status)

    app.include_router(
        create_integrations_router(
            get_integration,
            list_integrations,
            integration_crud,
            provider_catalog=provider_catalog,
            base_public_url=resolved_base,
        )
    )
    app.include_router(
        create_connections_router(
            list_connections, get_connection, connection_crud
        )
    )
    app.include_router(create_proxy_router(proxy_request))
    app.include_router(
        create_connect_sessions_router(
            create_connect_session,
            get_connect_session,
            delete_connect_session,
        )
    )
    app.include_router(
        create_auth_flows_router(
            create_auth_connection,
            integration_repository=integration_repo,
            provider_catalog=provider_catalog,
            connection_repository=connection_repo,
            callback_url_base=resolved_base,
        )
    )
    app.include_router(create_orchestrator_router(orchestrator_service))
    app.include_router(
        create_sync_control_router(orchestrator_service, integration_repo)
    )
    app.include_router(create_webhook_router())
    app.include_router(create_mcp_router())
    app.include_router(create_remote_function_router())
    app.include_router(create_v1_passthrough_router())
    app.include_router(create_misc_router())
    app.include_router(create_jobs_callback_router(jobs_processor))
    app.include_router(create_persist_router(records_repository))
    app.include_router(
        create_public_records_router(records_repository, connection_repo)
    )
    app.include_router(create_deploy_router())
    return app