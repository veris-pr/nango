"""Provider catalog loaded from the authoritative ``providers.yaml``.

Mirrors ``packages/providers/lib/index.ts`` ``loadProvidersYaml``:
- entries with an ``alias`` key merge the base provider's fields with the
  alias entry's overrides (overrides win), and the ``alias`` key is dropped;
- the result is a flat ``name -> entry`` map of full provider dicts.

Two views are exposed:
- :meth:`YamlProviderCatalog.get` returns the slim :class:`Provider` domain
  object (used by the integration-read use case).
- :meth:`YamlProviderCatalog.entry` / :meth:`YamlProviderCatalog.entries`
  return the full merged dict (used by the ``/providers`` routes, which spread
  the whole provider object into the response).

Localization (Accept-Language overrides) is intentionally not applied here;
callers get the base catalog. Add localized overlays when a boundary needs them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from nango_py.integrations.domain.provider import Provider

DEFAULT_PROVIDERS_PATH = (
    Path(__file__).resolve().parents[5]
    / "packages"
    / "providers"
    / "providers.yaml"
)


def _str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


class YamlProviderCatalog:
    """In-memory provider catalog implementing :class:`ProviderCatalog`."""

    def __init__(self, entries: dict[str, dict[str, Any]]) -> None:
        self._entries = entries

    def get(self, name: str) -> Provider | None:
        entry = self._entries.get(name)
        if entry is None:
            return None
        return _to_provider(name, entry)

    def entry(self, name: str) -> dict[str, Any] | None:
        return self._entries.get(name)

    def entries(self) -> dict[str, dict[str, Any]]:
        return self._entries

    @classmethod
    def from_path(cls, path: str | Path) -> YamlProviderCatalog:
        raw = yaml.safe_load(Path(path).read_text())
        if not isinstance(raw, dict):
            raise RuntimeError("providers.yaml must be a mapping of provider name -> entry")
        return cls(_resolve_aliases(raw))

    @classmethod
    def default(cls) -> YamlProviderCatalog:
        return cls.from_path(DEFAULT_PROVIDERS_PATH)


def _resolve_aliases(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for name, entry in raw.items():
        if isinstance(entry, dict) and "alias" not in entry:
            entries[name] = dict(entry)

    for name, entry in raw.items():
        if not isinstance(entry, dict) or "alias" not in entry:
            continue
        base_name = entry.get("alias")
        base = entries.get(base_name) if isinstance(base_name, str) else None
        overrides = {k: v for k, v in entry.items() if k != "alias"}
        merged = {**(base or {}), **overrides}
        entries[name] = merged

    return entries


def _to_provider(name: str, entry: dict[str, Any]) -> Provider:
    return Provider(
        name=name,
        display_name=_str(entry.get("display_name")) or name,
        auth_mode=_str(entry.get("auth_mode")) or "",
        webhook_routing_script=_str(entry.get("webhook_routing_script")),
    )