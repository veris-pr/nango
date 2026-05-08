from __future__ import annotations

import json
from typing import Any


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_json(value: Any) -> str:
    return (
        json.dumps(value, indent=2, sort_keys=True, separators=(",", ": "), ensure_ascii=False)
        + "\n"
    )
