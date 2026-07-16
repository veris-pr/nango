"""Template interpolation for proxy URL and header templates.

Mirrors the TS ``interpolateIfNeeded`` / ``getStableInterpolationReplacers``:
replace ``${key}`` with ``replacers[key]`` (stringified). Unmatched placeholders
are left as-is. ``connectionConfig.<name>`` resolves from a nested dict.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def interpolate(template: str, replacers: dict[str, Any]) -> str:
    if not isinstance(template, str) or "${" not in template:
        return template

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key.startswith("connectionConfig."):
            field = key[len("connectionConfig.") :]
            value = replacers.get("connectionConfig", {})
            if isinstance(value, dict) and field in value:
                return _to_str(value[field])
            return match.group(0)
        if key in replacers:
            return _to_str(replacers[key])
        return match.group(0)

    return _PLACEHOLDER.sub(_replace, _to_str(template))


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)