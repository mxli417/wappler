"""Configuration validation without local credentials."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from wappler.api import create_app
from wappler.utils import config


@pytest.mark.parametrize(
    "changes",
    [
        {"openai_api_key": ""},
        {"twilio_token": ""},
        {"allowed_senders": ()},
        {"whatsapp_from": "+15550000001"},
        {"allowed_senders": ("whatsapp:+abc",)},
        {"webhook_url": "http://example.com/v0/twilio"},
        {"webhook_url": "https://example.com/"},
        {"webhook_url": "", "environment": "production"},
        {"sender_hourly_limit": 11},
        {"sender_hourly_limit": 0},
        {"global_daily_limit": 0},
        {"worker_concurrency": 5},
        {"database_url": "https://database.invalid"},
        {"environment": "production"},
    ],
)
def test_invalid_settings(settings, changes):
    with pytest.raises(ValueError):
        replace(settings, **changes).validate()


def test_no_secrets_in_repr(settings):
    assert settings.openai_api_key not in repr(settings)
    assert settings.twilio_token not in repr(settings)


def test_missing_settings_prevent_start(settings):
    with pytest.raises(ValueError, match="TWILIO_TOKEN"):
        with TestClient(create_app(replace(settings, twilio_token=""))):
            pass


def test_env_precedence_and_legacy_fallback(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("TWILIO_TOKEN=dotenv-token\n", encoding="utf-8")
    monkeypatch.setattr(config, "get_project_root", lambda: tmp_path)
    monkeypatch.setenv("TWILIO_TOKEN", "environment-token")
    monkeypatch.delenv("TWILIO_WHATSAPP_FROM", raising=False)
    monkeypatch.setenv("TWILIO_TEST_MSG_FROM", "whatsapp:+15550000001")
    monkeypatch.setenv("ALLOWED_WHATSAPP_SENDERS", "whatsapp:+15550000002, whatsapp:+15550000003")
    settings = config.Settings.from_env()
    assert settings.twilio_token == "environment-token"
    assert settings.whatsapp_from == "whatsapp:+15550000001"
    assert len(settings.allowed_senders) == 2
