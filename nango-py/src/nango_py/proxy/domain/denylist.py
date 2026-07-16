"""Base URL override denylist.

Mirrors ``packages/server/lib/controllers/proxy/baseUrlOverrideDenylist.ts``:
canonicalize hostnames, normalize a denylist list, and check if an override
URL's hostname is denied. Fail-closed when a denylist is configured but the
override URL cannot be parsed.
"""

from __future__ import annotations

from urllib.parse import urlparse


def canonicalize_hostname(host: str) -> str:
    """Lowercase, strip brackets (IPv6), strip trailing FQDN dot."""
    h = host.strip().lower()
    if h.startswith("[") and h.endswith("]"):
        h = h[1:-1]
    while h.endswith("."):
        h = h[:-1]
    return h


def normalize_denylist_host(entry: str) -> str:
    """Normalize a denylist entry to a lowercase hostname."""
    trimmed = entry.strip()
    if not trimmed:
        return ""
    if "://" in trimmed:
        return canonicalize_hostname(urlparse(trimmed).hostname or "")
    try:
        return canonicalize_hostname(urlparse(f"http://{trimmed}").hostname or "")
    except Exception:
        return canonicalize_hostname(trimmed)


def normalize_denylist(denylist: list[str] | None) -> set[str]:
    if not denylist:
        return set()
    return {h for e in denylist if (h := normalize_denylist_host(e))}


def is_base_url_override_denied(override_url: str, denylist: set[str]) -> bool:
    if not denylist:
        return False
    try:
        hostname = canonicalize_hostname(urlparse(override_url).hostname or "")
    except Exception:
        return True
    return hostname in denylist