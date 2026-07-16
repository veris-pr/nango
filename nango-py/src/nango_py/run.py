"""Local server startup — reads env vars and calls create_app.

Usage:
  NANGO_DATABASE_URL=postgresql://... python -m nango_py.run
  uv run python -m nango_py.run
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from nango_py.server.app import create_app


def _rebuild_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def main() -> None:
    db_url = os.environ.get("NANGO_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("NANGO_DATABASE_URL or DATABASE_URL is required")

    engine = create_async_engine(
        _rebuild_url(db_url),
        connect_args={
            "server_settings": {
                "search_path": os.environ.get("NANGO_DB_SCHEMA", "nango"),
            },
        },
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    app = create_app(
        session_factory=session_factory,
        encryption_key=os.environ.get("NANGO_ENCRYPTION_KEY", ""),
    )

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("SERVER_PORT", "8000")))


if __name__ == "__main__":
    main()