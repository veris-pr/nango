from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from os import environ
from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nango.adapters.database import (
    DatabaseSettings,
    check_database_health,
    create_engine,
    create_session_factory,
    transaction,
)
from nango.api import PublicAPIService, create_public_api_router
from nango.auth.service import AuthService
from nango.domain.postgres_repositories import (
    PostgresConnectionRepository,
    PostgresIntegrationConfigRepository,
    PostgresSyncRepository,
)
from nango.domain.repositories import InMemoryIntegrationConfigRepository
from nango.orchestrator import OrchestratorService, create_orchestrator_router
from nango.persist import PersistService, create_persist_router
from nango.records import PostgresRecordsRepository
from nango.server.health import HealthResponse
from nango.server.settings import Settings
from nango.utils.errors import ApplicationError


def create_app(
    settings: Settings | None = None,
    *,
    orchestrator_service: OrchestratorService | None = None,
    persist_service: PersistService | None = None,
    public_api_service: PublicAPIService | None = None,
) -> FastAPI:
    app_settings = settings or Settings.from_env()
    database_settings = _database_settings(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        app.state.db_engine = None
        app.state.db_session_factory = None
        app.state.auth_service = AuthService(settings=app_settings)
        app.state.integration_repository = InMemoryIntegrationConfigRepository()
        app.state.connection_repository = None
        app.state.sync_repository = None
        if database_settings is None:
            yield
            return

        engine = create_engine(database_settings)
        app.state.db_engine = engine
        app.state.db_session_factory = create_session_factory(engine)
        app.state.auth_service = AuthService(
            session_factory=app.state.db_session_factory,
            settings=app_settings,
        )
        if public_api_service is None:
            integration_repository = PostgresIntegrationConfigRepository(
                app.state.db_session_factory
            )
            connection_repository = PostgresConnectionRepository(
                app.state.db_session_factory,
                encryption_key=app_settings.encryption_key,
            )
            sync_repository = PostgresSyncRepository(app.state.db_session_factory)
            app.state.integration_repository = integration_repository
            app.state.connection_repository = connection_repository
            app.state.sync_repository = sync_repository
            public_api.integrations = integration_repository
            public_api.connections = connection_repository
            public_api.syncs = sync_repository
        if persist_service is None:
            persist.records_repository = PostgresRecordsRepository(app.state.db_session_factory)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title=app_settings.service_name, lifespan=lifespan)
    if orchestrator_service is not None:
        orchestrator = orchestrator_service
    elif public_api_service is not None:
        orchestrator = public_api_service.orchestrator
    else:
        orchestrator = OrchestratorService()
    persist = persist_service or PersistService()
    public_api = public_api_service or PublicAPIService(
        orchestrator=orchestrator,
        integrations=InMemoryIntegrationConfigRepository(),
    )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        _request: object,
        exc: ApplicationError,
    ) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_api_error())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: object,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": "Request validation failed",
                    "errors": exc.errors(),
                }
            },
        )

    app.include_router(create_orchestrator_router(orchestrator))
    app.include_router(create_persist_router(persist))

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        session_factory = _database_session_factory(app)
        if session_factory is not None:
            async with transaction(session_factory) as session:
                healthy = await check_database_health(session)
            if not healthy:
                raise ApplicationError(
                    "database_unavailable",
                    message="Database health check failed",
                    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                )
        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            cutover_mode=app_settings.cutover_mode,
        )

    app.include_router(create_public_api_router(public_api))

    return app


def _database_settings(app_settings: Settings) -> DatabaseSettings | None:
    if app_settings.database_url:
        environment = dict(environ)
        environment["NANGO_DATABASE_URL"] = app_settings.database_url
        environment.setdefault("NANGO_DB_APPLICATION_NAME", app_settings.service_name)
        return DatabaseSettings.from_env(environment)

    if any(
        environ.get(key)
        for key in (
            "NANGO_DATABASE_URL",
            "NANGO_DB_HOST",
            "NANGO_DB_USER",
            "NANGO_DB_PASSWORD",
            "NANGO_DB_NAME",
            "NANGO_DB_PORT",
        )
    ):
        environment = dict(environ)
        environment.setdefault("NANGO_DB_APPLICATION_NAME", app_settings.service_name)
        return DatabaseSettings.from_env(environment)

    return None


def _database_session_factory(
    app: FastAPI,
) -> async_sessionmaker[AsyncSession] | None:
    session_factory = getattr(app.state, "db_session_factory", None)
    return cast(async_sessionmaker[AsyncSession] | None, session_factory)
