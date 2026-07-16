import logging

import pytest

from nango.adapters.email import (
    EmailClient,
    MailgunEmailProvider,
    NoopEmailProvider,
    SmtpEmailProvider,
    create_email_provider,
)


def test_email_selector_defaults_to_noop_provider() -> None:
    assert isinstance(create_email_provider({}), NoopEmailProvider)


def test_noop_provider_logs_without_sending(caplog: pytest.LogCaptureFixture) -> None:
    provider = NoopEmailProvider()

    with caplog.at_level(logging.INFO):
        provider.send("user@example.com", "Subject", "<p>Hello</p>")

    assert "Email client not configured" in caplog.text


def test_email_selector_uses_explicit_unimplemented_placeholders() -> None:
    assert isinstance(create_email_provider({"MAILGUN_API_KEY": "key"}), MailgunEmailProvider)
    assert isinstance(create_email_provider({"SMTP_URL": "smtp://example"}), SmtpEmailProvider)


def test_unimplemented_provider_send_fails_explicitly() -> None:
    client = EmailClient.from_environment({"SMTP_URL": "smtp://example"})

    with pytest.raises(NotImplementedError, match="smtp email provider is not implemented"):
        client.send("user@example.com", "Subject", "<p>Hello</p>")
