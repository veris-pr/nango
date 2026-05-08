from __future__ import annotations

from collections.abc import Iterable

from nango.nango_yaml.models import ParserIssue


class NangoYamlParseError(ValueError):
    def __init__(self, issues: Iterable[ParserIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)
        super().__init__(summary or "Invalid nango.yaml")
