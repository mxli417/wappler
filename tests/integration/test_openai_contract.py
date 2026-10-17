"""Run the real SDK against a local mock transport; no key or API bill needed."""

from email import policy
from email.parser import BytesParser

import httpx2 as httpx
import pytest
from openai import APIStatusError, APITimeoutError, OpenAI

from wappler.speech2text import whispr


@pytest.mark.parametrize("filename", ["human_audio_ger.m4a", "human_audio_ger.ogg"])
def test_sdk_upload_and_response(test_audio_path, filename, monkeypatch):
    audio_path = test_audio_path / filename
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v1/audio/transcriptions"
        assert request.headers["authorization"] == "Bearer offline-test-key"
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + request.headers["content-type"] + "\r\n\r\n").encode() + request.read()
        )
        parts = {part.get_param("name", header="content-disposition"): part for part in message.iter_parts()}
        assert parts["model"].get_payload(decode=True) == b"whisper-1"
        assert parts["file"].get_filename() == filename
        assert parts["file"].get_payload(decode=True) == audio_path.read_bytes()
        return httpx.Response(200, json={"text": "Moin, ich bin Max."})

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="offline-test-key",
        base_url="https://openai.invalid/v1",
        http_client=transport_client,
        max_retries=0,
        timeout=30,
    )
    monkeypatch.setattr(whispr, "get_client", lambda key: client)
    assert whispr.openai_transcribe(audio_path, "offline-test-key").text == "Moin, ich bin Max."
    assert len(requests) == 1
    assert transport_client.is_closed


@pytest.mark.parametrize("failure", [401, 429, 500, "timeout"])
def test_sdk_failures_propagate_without_retry(test_audio_path, monkeypatch, failure):
    requests = []

    def handler(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("Simulated timeout", request=request)
        return httpx.Response(failure, json={"error": {"message": "Simulated failure", "type": "test_error"}})

    transport_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAI(
        api_key="offline-test-key",
        base_url="https://openai.invalid/v1",
        http_client=transport_client,
        max_retries=0,
        timeout=30,
    )
    monkeypatch.setattr(whispr, "get_client", lambda key: client)
    error = APITimeoutError if failure == "timeout" else APIStatusError
    with pytest.raises(error):
        whispr.openai_transcribe(test_audio_path / "human_audio_ger.m4a", "offline-test-key")
    assert len(requests) == 1
    assert transport_client.is_closed
