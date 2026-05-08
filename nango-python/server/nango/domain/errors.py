from __future__ import annotations

from http import HTTPStatus

from nango.utils.errors import ApplicationError


def domain_not_found(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message=message, status_code=HTTPStatus.NOT_FOUND)


def domain_conflict(code: str, message: str) -> ApplicationError:
    return ApplicationError(code, message=message, status_code=HTTPStatus.CONFLICT)


def provider_not_found(provider: str) -> ApplicationError:
    return domain_not_found(
        "provider_not_found",
        f'Provider "{provider}" was not found',
    )


def integration_not_found(provider_config_key: str) -> ApplicationError:
    return domain_not_found(
        "integration_not_found",
        f'Integration "{provider_config_key}" was not found',
    )


def integration_already_exists(provider_config_key: str) -> ApplicationError:
    return domain_conflict(
        "integration_already_exists",
        f'Integration "{provider_config_key}" already exists',
    )
