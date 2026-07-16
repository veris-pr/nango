"""Shared serialization helpers.

``iso`` mirrors ``Date.toISOString()`` (ISO 8601 with a ``Z`` suffix). The
differential harness normalizes sub-second precision.
"""

from __future__ import annotations

from datetime import datetime


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat().replace("+00:00", "Z")


def iso_required(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")