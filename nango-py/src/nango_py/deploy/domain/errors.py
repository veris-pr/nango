"""Deploy errors."""

from __future__ import annotations

from nango_py.shared.errors import ApiError


class MissingNangoYaml(ApiError):
    status = 400
    code = "missing_nango_yaml"
    message = 'Request body must include "yaml" or "nangoYaml"'


class ConcurrentDeployment(ApiError):
    status = 409
    code = "concurrent_deployment"
    message = "A deployment is already in progress for this environment"