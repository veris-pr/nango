from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[4]
PROVIDERS_ROOT = REPO_ROOT / "packages" / "providers"
DEFAULT_PROVIDERS_YAML = PROVIDERS_ROOT / "providers.yaml"
DEFAULT_PROVIDER_SCOPES_YAML = PROVIDERS_ROOT / "providers.scopes.yaml"
DEFAULT_I18N_DIR = PROVIDERS_ROOT / "i18n"

Provider = dict[str, Any]
ProviderCatalog = dict[str, Provider]


def load_providers_yaml(
    path: Path | None = None,
    *,
    language: str | None = None,
    i18n_dir: Path | None = None,
) -> ProviderCatalog:
    providers = _expand_aliases(_read_yaml_mapping(path or DEFAULT_PROVIDERS_YAML))
    if language is None:
        return providers

    return get_localized_providers(providers, language, i18n_dir=i18n_dir)


def get_provider(provider_name: str, *, language: str | None = None) -> Provider | None:
    return load_providers_yaml(language=language).get(provider_name)


def load_provider_scopes_yaml(path: Path | None = None) -> dict[str, list[str]]:
    scopes = _read_yaml_mapping(path or DEFAULT_PROVIDER_SCOPES_YAML)
    return {
        key: cast(list[str], value)
        for key, value in scopes.items()
        if isinstance(value, list)
    }


def load_language_overrides(language: str, *, i18n_dir: Path | None = None) -> dict[str, Any]:
    language_file = (i18n_dir or DEFAULT_I18N_DIR) / f"providers.{language}.json"
    if not language_file.exists():
        return {}

    payload = json.loads(language_file.read_text())
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{language_file} must contain a JSON object")
    return cast(dict[str, Any], payload)


def get_localized_providers(
    providers: ProviderCatalog,
    language: str,
    *,
    i18n_dir: Path | None = None,
) -> ProviderCatalog:
    overrides = load_language_overrides(language, i18n_dir=i18n_dir)
    return cast(ProviderCatalog, _deep_merge(providers, overrides))


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text())
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return cast(dict[str, Any], payload)


def _expand_aliases(entries: dict[str, Any]) -> ProviderCatalog:
    providers: ProviderCatalog = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"Provider {name} must be a mapping")

        raw_provider = cast(Provider, entry)
        alias = raw_provider.get("alias")
        if isinstance(alias, str):
            provider = _aliased_provider(name, alias, raw_provider, entries)
        else:
            provider = copy.deepcopy(raw_provider)

        providers[name] = provider

    return providers


def _aliased_provider(
    name: str,
    alias: str,
    raw_provider: Provider,
    entries: dict[str, Any],
) -> Provider:
    alias_entry = entries.get(alias)
    if not isinstance(alias_entry, dict):
        raise ValueError(f"Provider {name} aliases missing provider {alias}")

    provider = copy.deepcopy(cast(Provider, alias_entry))
    provider.update(
        {
            key: copy.deepcopy(value)
            for key, value in raw_provider.items()
            if key != "alias"
        }
    )
    return provider


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(target)
    for key, value in source.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(
                cast(dict[str, Any], current),
                cast(dict[str, Any], value),
            )
        else:
            result[key] = copy.deepcopy(value)
    return result


__all__ = [
    "DEFAULT_I18N_DIR",
    "DEFAULT_PROVIDER_SCOPES_YAML",
    "DEFAULT_PROVIDERS_YAML",
    "Provider",
    "ProviderCatalog",
    "get_localized_providers",
    "get_provider",
    "load_language_overrides",
    "load_provider_scopes_yaml",
    "load_providers_yaml",
]
