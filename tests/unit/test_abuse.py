"""No vendor work before authentication, admission and media guard checks."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.parse import urlencode

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from wappler.api import MAX_WEBHOOK_BYTES, bounded_form, create_app
from wappler.speech2text import whispr


def test_replay_and_eleventh_operation(signed_post, form, vendors, drain):
    for number in range(10):
        form["MessageSid"] = f"SM{number}"
        assert signed_post(form).status_code == 200
    assert signed_post(form).status_code == 200  # duplicate
    form["MessageSid"] = "SM11"
    response = signed_post(form)
    assert response.status_code == 429
    assert response.headers["retry-after"]
    drain()
    assert vendors[0].call_count == vendors[1].call_count == 10


def test_oversized_actual_body_and_repeated_fields(client, form, vendors):
    headers = {"Content-Type": "application/x-www-form-urlencoded", "X-Twilio-Signature": "present"}
    assert client.post("/v0/twilio", content=b"x" * (MAX_WEBHOOK_BYTES + 1), headers=headers).status_code == 413
    assert client.post("/v0/twilio", content=urlencode(form) + "&From=other", headers=headers).status_code == 400
    assert (
        client.post("/v0/twilio", content="&".join(f"x{i}=1" for i in range(101)), headers=headers).status_code == 400
    )
    vendors[0].assert_not_called()


def test_chunked_size_limit_without_length():
    async def run():
        async def receive():
            return {"type": "http.request", "body": b"x" * 20000, "more_body": True}

        req = Request({"type": "http", "headers": []}, receive)
        with pytest.raises(HTTPException) as error:
            await bounded_form(req)
        assert error.value.status_code == 413

    asyncio.run(run())


def test_query_tampering_and_hidden_endpoints(client, settings, form):
    from twilio.request_validator import RequestValidator

    signature = RequestValidator(settings.twilio_token).compute_signature(settings.webhook_url, form)
    assert client.post("/v0/twilio?extra=1", data=form, headers={"X-Twilio-Signature": signature}).status_code == 403
    for path in ("/stats", "/docs", "/openapi.json"):
        assert client.get(path).status_code == 404


def test_admission_and_readiness_fail_closed(client, signed_post, form, monkeypatch, vendors):
    monkeypatch.setattr(client.app.state.store, "admit", Mock(side_effect=RuntimeError("private database URL")))
    response = signed_post(form)
    assert response.status_code == 503 and "private" not in response.text
    vendors[0].assert_not_called()
    monkeypatch.setattr(client.app.state.store, "snapshot", Mock(side_effect=RuntimeError("private")))
    assert client.get("/ready").status_code == 503
    assert client.get("/heartbeat").status_code == 200


def test_disabled_and_full_fail_closed(settings, form):
    from twilio.request_validator import RequestValidator

    signature = RequestValidator(settings.twilio_token).compute_signature(settings.webhook_url, form)
    with TestClient(create_app(replace(settings, processing_enabled=False))) as client:
        assert client.post("/v0/twilio", data=form, headers={"X-Twilio-Signature": signature}).status_code == 503


@pytest.mark.parametrize("seconds", [0, -1, 301, float("nan"), float("inf")])
def test_duration_rejects_before_paid_call(monkeypatch, tmp_path, seconds):
    monkeypatch.setattr(whispr.mutagen, "File", lambda _: SimpleNamespace(info=SimpleNamespace(length=seconds)))
    with pytest.raises(ValueError, match="duration"):
        whispr.validate_duration(tmp_path / "audio.ogg", 300)


def test_real_audio_duration_and_invalid_audio(test_audio_path, tmp_path):
    for filename in ("human_audio_ger.m4a", "human_audio_ger.ogg"):
        whispr.validate_duration(test_audio_path / filename, 300)
        with pytest.raises(ValueError):
            whispr.validate_duration(test_audio_path / filename, 1)
    invalid = tmp_path / "audio.ogg"
    invalid.write_bytes(b"not audio")
    with pytest.raises(ValueError):
        whispr.validate_duration(invalid, 300)


def response(status, location=""):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status_code = status
    result.headers = {"Location": location}
    result.iter_content.return_value = [b"audio"]
    return result


def test_redirect_to_private_host_never_requested(monkeypatch, tmp_path):
    get = Mock(return_value=response(302, "http://127.0.0.1/private"))
    monkeypatch.setattr(whispr.requests, "get", get)
    with pytest.raises(ValueError):
        whispr.download_audio("https://api.twilio.com/media", tmp_path / "audio", "sid", "token")
    assert get.call_count == 1


def test_cdn_redirect_strips_auth_and_redirect_count_is_bounded(monkeypatch, tmp_path):
    get = Mock(side_effect=[response(302, "https://mms.twiliocdn.com/signed"), response(200)])
    monkeypatch.setattr(whispr.requests, "get", get)
    whispr.download_audio("https://api.twilio.com/media", tmp_path / "audio", "sid", "token")
    assert get.call_args_list[0].kwargs["auth"] == ("sid", "token")
    assert get.call_args_list[1].kwargs["auth"] is None
    assert not get.call_args.kwargs["allow_redirects"]
    get.side_effect = None
    get.return_value = response(302, "https://api.twilio.com/loop")
    with pytest.raises(ValueError, match="redirects"):
        whispr.download_audio("https://api.twilio.com/media", tmp_path / "audio", "sid", "token")
