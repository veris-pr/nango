from typing import Any


def interpolate_string(template: str, credentials: dict, connection_config: dict) -> str:
    """Interpolate template with credentials and connection config."""
    all_vars = {**credentials, **connection_config}
    result = template
    for key, value in all_vars.items():
        if value:
            result = result.replace(f'${{{key}}}', str(value))
    return result