from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

LOGGER = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def send(self, email: str, subject: str, html: str) -> None: ...


class NoopEmailProvider:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or LOGGER

    def send(self, email: str, subject: str, html: str) -> None:
        self._logger.info("Email client not configured")
        self._logger.info("The following email would have been sent:")
        self._logger.info("%s %s", email, subject)
        self._logger.info("%s", html)


@dataclass(frozen=True, slots=True)
class ProviderNotImplemented:
    provider_name: str

    def send(self, email: str, subject: str, html: str) -> None:
        raise NotImplementedError(
            f"{self.provider_name} email provider is not implemented in Python core"
        )


class MailgunEmailProvider(ProviderNotImplemented):
    def __init__(self) -> None:
        super().__init__("mailgun")


class SmtpEmailProvider(ProviderNotImplemented):
    def __init__(self) -> None:
        super().__init__("smtp")


def create_email_provider(environ: Mapping[str, str] | None = None) -> EmailProvider:
    env = os.environ if environ is None else environ
    if env.get("MAILGUN_API_KEY"):
        return MailgunEmailProvider()
    if env.get("SMTP_URL"):
        return SmtpEmailProvider()
    return NoopEmailProvider()


class EmailClient:
    def __init__(self, provider: EmailProvider | None = None) -> None:
        self._provider = provider or create_email_provider()

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> EmailClient:
        return cls(create_email_provider(environ))

    def send(self, email: str, subject: str, html: str) -> None:
        self._provider.send(email, subject, html)


__all__ = [
    "EmailClient",
    "EmailProvider",
    "MailgunEmailProvider",
    "NoopEmailProvider",
    "ProviderNotImplemented",
    "SmtpEmailProvider",
    "create_email_provider",
]
