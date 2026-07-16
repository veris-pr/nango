"""YamlProviderCatalog: alias resolution and field extraction."""

from __future__ import annotations

from pathlib import Path

from nango_py.integrations.infrastructure.provider_catalog import YamlProviderCatalog

REAL_PATH = (
    Path(__file__).resolve().parents[4]
    / "packages"
    / "providers"
    / "providers.yaml"
)


def _write_catalog(tmp_path: Path, body: str) -> YamlProviderCatalog:
    path = tmp_path / "providers.yaml"
    path.write_text(body)
    return YamlProviderCatalog.from_path(path)


def test_extracts_base_provider_fields(tmp_path: Path) -> None:
    catalog = _write_catalog(
        tmp_path,
        """
github:
    display_name: GitHub
    auth_mode: OAUTH2
    webhook_routing_script: githubWebhookRouting
""",
    )
    provider = catalog.get("github")
    assert provider is not None
    assert provider.display_name == "GitHub"
    assert provider.auth_mode == "OAUTH2"
    assert provider.webhook_routing_script == "githubWebhookRouting"


def test_alias_merges_base_with_overrides(tmp_path: Path) -> None:
    catalog = _write_catalog(
        tmp_path,
        """
adp:
    display_name: ADP
    auth_mode: OAUTH2
adp-lyric:
    alias: adp
    display_name: ADP Lyric
""",
    )
    provider = catalog.get("adp-lyric")
    assert provider is not None
    assert provider.display_name == "ADP Lyric"  # override wins
    assert provider.auth_mode == "OAUTH2"  # inherited from base


def test_display_name_falls_back_to_provider_name(tmp_path: Path) -> None:
    catalog = _write_catalog(
        tmp_path,
        """
basic:
    auth_mode: API_KEY
""",
    )
    provider = catalog.get("basic")
    assert provider is not None
    assert provider.display_name == "basic"
    assert provider.auth_mode == "API_KEY"


def test_unknown_provider_returns_none(tmp_path: Path) -> None:
    catalog = _write_catalog(tmp_path, "github:\n    auth_mode: OAUTH2\n")
    assert catalog.get("ghost") is None


def test_loads_real_providers_yaml_smoke() -> None:
    if not REAL_PATH.exists():
        raise AssertionError(f"real providers.yaml not found at {REAL_PATH}")
    catalog = YamlProviderCatalog.from_path(REAL_PATH)
    github = catalog.get("github")
    assert github is not None
    assert github.auth_mode == "OAUTH2"