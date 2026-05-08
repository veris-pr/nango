from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from nango.api import PublicAPIService, create_public_api_router
from nango.orchestrator import OrchestratorService, create_orchestrator_router
from nango.persist import PersistService, create_persist_router
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
    app = FastAPI(title=app_settings.service_name)
    if orchestrator_service is not None:
        orchestrator = orchestrator_service
    elif public_api_service is not None:
        orchestrator = public_api_service.orchestrator
    else:
        orchestrator = OrchestratorService()
    public_api = public_api_service or PublicAPIService(orchestrator=orchestrator)

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
    app.include_router(create_persist_router(persist_service))

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=app_settings.service_name,
            cutover_mode=app_settings.cutover_mode,
        )

    app.include_router(create_public_api_router(public_api))

    return app
