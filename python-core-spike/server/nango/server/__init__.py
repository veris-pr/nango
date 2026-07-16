from collections.abc import Callable
from typing import Any, cast

__all__ = ["create_app"]


def create_app(*args: Any, **kwargs: Any) -> Any:
    from nango.server.app import create_app as _create_app

    return cast(Callable[..., Any], _create_app)(*args, **kwargs)
