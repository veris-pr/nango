from httpx import ASGITransport, AsyncClient

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
