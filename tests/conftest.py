"""Offline defaults: vendor network calls require an explicit --live flag."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from wappler import api, worker
from wappler.utils.config import Settings


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="Enable tests that call paid APIs and send WhatsApp messages")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--live"):
        for item in items:
            if "live" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Requires explicit --live"))


@pytest.fixture(autouse=True)
def block_external_network(request, monkeypatch):
    if request.node.get_closest_marker("live") and request.config.getoption("--live"):
        return

    def blocked(*args, **kwargs):
        raise AssertionError("External network is disabled in offline tests")

    monkeypatch.setattr("requests.sessions.Session.request", blocked)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", blocked)
    monkeypatch.setattr("httpx2.HTTPTransport.handle_request", blocked)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        openai_api_key="test-key",
        twilio_token="test-token",
        twilio_sid="ACtest",
        whatsapp_from="whatsapp:+15550000001",
        allowed_senders=("whatsapp:+15550000002",),
        webhook_url="https://example.com/v0/twilio",
        database_url=f"sqlite:///{tmp_path / 'jobs.db'}",
        worker_enabled=False,
    )


@pytest.fixture
def form(settings):
    return {
        "From": settings.allowed_senders[0],
        "To": settings.whatsapp_from,
        "AccountSid": settings.twilio_sid,
        "MessageSid": "SMtest",
        "NumMedia": "1",
        "MediaUrl0": "https://api.twilio.com/media/test",
        "MediaContentType0": "audio/ogg",
    }


@pytest.fixture
def vendors(monkeypatch):
    transcribe = Mock(return_value="Hello from a voice note.")
    send = Mock(return_value="SMreply")
    monkeypatch.setattr(worker, "transcribe_urlmedia", transcribe)
    monkeypatch.setattr(worker, "create_wapp_msg", send)
    return transcribe, send


@pytest.fixture
def client(settings, vendors):
    with TestClient(api.create_app(settings)) as instance:
        yield instance


@pytest.fixture
def signed_post(client, settings):
    def post(data, signature_url=None):
        signature = RequestValidator(settings.twilio_token).compute_signature(
            signature_url or settings.webhook_url, data
        )
        return client.post("/v0/twilio", data=data, headers={"X-Twilio-Signature": signature})

    return post


@pytest.fixture
def drain(client):
    def run():
        while job := client.app.state.store.claim():
            worker.process_job(client.app.state.store, job)

    return run


@pytest.fixture(scope="session")
def test_audio_path():
    return Path(__file__).parent / "assets" / "audio"
