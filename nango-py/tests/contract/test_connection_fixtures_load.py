"""Connection fixtures must parse and carry the required envelope keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parent / "connections" / "fixtures"

REQUIRED_TOP = {"scenario", "request", "response"}
REQUIRED_REQUEST = {"method", "path", "headers", "query"}
REQUIRED_RESPONSE = {"status", "body"}


def _load_each() -> list[tuple[Path, dict[str, Any]]]:
    return [(path, json.loads(path.read_text())) for path in sorted(FIXTURE_DIR.glob("*.json"))]


def test_fixture_directory_exists() -> None:
    assert FIXTURE_DIR.is_dir(), f"missing fixture dir: {FIXTURE_DIR}"


def test_fixtures_have_required_keys() -> None:
    cases = _load_each()
    assert cases, "no connection contract fixtures found"
    for path, fixture in cases:
        _assert_required(path, fixture, REQUIRED_TOP, "top")
        _assert_required(path, fixture["request"], REQUIRED_REQUEST, "request")
        _assert_required(path, fixture["response"], REQUIRED_RESPONSE, "response")
        assert isinstance(fixture["response"]["status"], int), f"{path.name}: status not int"


def test_scenarios_are_unique() -> None:
    scenarios = [fixture["scenario"] for _, fixture in _load_each()]
    assert len(scenarios) == len(set(scenarios)), "duplicate scenario names"


def _assert_required(path: Path, payload: dict[str, Any], required: set[str], label: str) -> None:
    missing = required - payload.keys()
    assert not missing, f"{path.name}: {label} missing keys {missing}"