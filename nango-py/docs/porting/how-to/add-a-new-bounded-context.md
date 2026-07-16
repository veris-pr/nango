# How-to: Add a new bounded context

> **Task:** Create the DDD folder structure for a new service boundary.

A bounded context is a vertical slice of the system with its own domain,
application, infrastructure, and transport layers. Create one when a new
service boundary begins — not before.

## When to create a bounded context

Create a new bounded context when:
- A new service boundary starts (e.g., `webhooks`, `records`, `scheduler`)
- The feature has its own domain model, use cases, and storage
- It maps to a distinct TypeScript `packages/` boundary

Do **not** create one for a single route — add routes to existing contexts.

## Step 1 — Create the folder structure

```bash
mkdir -p src/nango_py/<context>/{domain,application,infrastructure,transport}
touch src/nango_py/<context>/__init__.py
touch src/nango_py/<context>/{domain,application,infrastructure,transport}/__init__.py
```

## Step 2 — Write the domain layer

`domain/` owns data shapes and invariants. No FastAPI, no SQLAlchemy, no Pydantic:

```python
# src/nango_py/<context>/domain/model.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class MyEntity:
    id: int
    name: str
    # ...
```

Add typed domain errors:

```python
# src/nango_py/<context>/domain/errors.py
from nango_py.shared.errors import ApiError

class MyNotFound(ApiError):
    status = 404
    code = "not_found"
    message = "Entity not found"
```

## Step 3 — Define application ports

`application/` owns use cases and Protocols for I/O:

```python
# src/nango_py/<context>/application/gateway.py
from typing import Protocol
from nango_py.<context>.domain.model import MyEntity

class MyRepository(Protocol):
    async def get_by_id(self, entity_id: int) -> MyEntity | None: ...
```

Write the use case:

```python
# src/nango_py/<context>/application/get_entity.py
from dataclasses import dataclass
from nango_py.auth.domain.context import AuthenticatedContext

@dataclass(frozen=True)
class GetEntityRequest:
    entity_id: int
    context: AuthenticatedContext

class GetEntity:
    def __init__(self, repository: MyRepository):
        self._repo = repository

    async def execute(self, request: GetEntityRequest) -> MyEntity:
        entity = await self._repo.get_by_id(request.entity_id)
        if entity is None:
            raise MyNotFound()
        return entity
```

## Step 4 — Implement the infrastructure adapter

`infrastructure/` owns SQLAlchemy repositories, external clients:

```python
# src/nango_py/<context>/infrastructure/sqlalchemy_repository.py
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

class SqlAlchemyMyRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._sf = session_factory

    async def get_by_id(self, entity_id: int) -> MyEntity | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    text("SELECT * FROM my_table WHERE id = :id"),
                    {"id": entity_id},
                )
            ).mappings().first()
        return _row_to_entity(row) if row else None
```

## Step 5 — Write the transport routes

`transport/` owns HTTP parsing, validation, and response mapping:

```python
# src/nango_py/<context>/transport/routes.py
from fastapi import APIRouter, Depends

def create_my_router(get_entity: GetEntity) -> APIRouter:
    router = APIRouter(tags=["my-context"])

    @router.get("/my-entity/{entity_id}")
    async def get_entity_route(
        entity_id: int,
        auth: Annotated[AuthenticatedContext, Depends(api_auth)],
    ) -> JSONResponse:
        entity = await get_entity.execute(
            GetEntityRequest(entity_id=entity_id, context=auth)
        )
        return JSONResponse({"data": _serialize(entity)})

    return router
```

## Step 6 — Wire into the composition root

In `server/app.py`:

```python
from nango_py.<context>.infrastructure.sqlalchemy_repository import SqlAlchemyMyRepository
from nango_py.<context>.application.get_entity import GetEntity
from nango_py.<context>.transport.routes import create_my_router

# In create_app():
my_repo = SqlAlchemyMyRepository(session_factory)
get_entity = GetEntity(repository=my_repo)
app.include_router(create_my_router(get_entity))
```

## Step 7 — Add tests

```bash
mkdir -p tests/unit/<context> tests/integration
touch tests/unit/<context>/__init__.py
```

Write unit tests for domain logic and integration tests against real Postgres.

## Dependency rules

```
transport  ──→  application  ──→  domain
infrastructure  ──→  application / domain ports
composition root  ──→  transport + infrastructure
```

Never:
- Import FastAPI in `domain/`
- Import SQLAlchemy in `domain/`
- Import Pydantic in `domain/`
- Import a concrete infrastructure adapter in `application/` (use Protocols)
- Branch on adapter type in use cases

## Checklist

- [ ] Folder structure with `__init__.py` files
- [ ] Domain: frozen dataclasses + typed errors
- [ ] Application: async Protocols + use cases
- [ ] Infrastructure: concrete SQLAlchemy adapter
- [ ] Transport: validate → use case → serialize
- [ ] Wired into `server/app.py`
- [ ] Unit + integration tests
- [ ] `ruff check .` passes
- [ ] `mypy` passes
- [ ] `pytest` passes