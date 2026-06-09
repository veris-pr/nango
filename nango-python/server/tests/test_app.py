from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from nango.server import app as app_module
from nango.server.app import create_app
from nango.server.settings import Settings


async def test_health_route_returns_service_status() -> None:
    app = create_app(Settings(service_name="test-core"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "test-core",
        "cutover_mode": "disabled",
    }


async def test_health_route_exposes_explicit_cutover_mode() -> None:
    app = create_app(Settings(service_name="test-core", cutover_mode="shadow"))
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["cutover_mode"] == "shadow"


async def test_health_route_checks_database_when_configured(monkeypatch) -> None:
    class FakeEngine:
        def __init__(self) -> None:
            self.disposed = False

        async def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()
    session_factory = object()
    health_check = AsyncMock(return_value=True)

    @asynccontextmanager
    async def fake_transaction(_session_factory: object):
        yield object()

    monkeypatch.setattr(app_module, "create_engine", lambda _settings: engine)
    monkeypatch.setattr(
        app_module,
        "create_session_factory",
        lambda _engine: session_factory,
    )
    monkeypatch.setattr(app_module, "transaction", fake_transaction)
    monkeypatch.setattr(app_module, "check_database_health", health_check)

    app = create_app(Settings(service_name="test-core", database_url="postgres://test"))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    assert health_check.await_count == 1
    assert engine.disposed is True
