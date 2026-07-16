import pytest
from pydantic import ValidationError

from nango.server.settings import Settings


def test_cutover_mode_defaults_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NANGO_PYTHON_CUTOVER_MODE", raising=False)

    assert Settings.from_env().cutover_mode == "disabled"


def test_cutover_mode_reads_explicit_environment_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANGO_PYTHON_CUTOVER_MODE", "canary")

    assert Settings.from_env().cutover_mode == "canary"


def test_cutover_mode_rejects_unknown_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANGO_PYTHON_CUTOVER_MODE", "proxy")

    with pytest.raises(ValidationError):
        Settings.from_env()
