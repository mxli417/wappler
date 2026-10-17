"""Audio boundary and cleanup tests with mocked vendor transports."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
import requests

from wappler.speech2text import whispr


def test_default_sdk_transport_is_blocked_offline(test_audio_path):
    """Catch SDK transport changes that could bypass the offline network guard."""
    with whispr.get_client("offline-test-key") as client:
        client.base_url = "https://openai.invalid/v1"
        assert client.max_retries == 0
        assert client.timeout == 30
        with (test_audio_path / "human_audio_ger.m4a").open("rb") as audio:
            with pytest.raises(AssertionError, match="External network is disabled"):
                client.audio.transcriptions.create(model="whisper-1", file=audio)


@pytest.mark.parametrize("size,valid", [(0, False), (1, True), (24 * 1024 * 1024, True), (24 * 1024 * 1024 + 1, False)])
def test_size_boundary(tmp_path, size, valid):
    audio = tmp_path / "audio.ogg"
    with audio.open("wb") as file:
        file.truncate(size)
    assert whispr.check_size(audio) is valid


def test_transcription_closes_file_and_client(tmp_path, monkeypatch):
    audio = tmp_path / "audio.ogg"
    audio.write_bytes(b"OggS")
    client = MagicMock()
    client.__enter__.return_value = client
    client.audio.transcriptions.create.return_value = SimpleNamespace(text="hello")
    monkeypatch.setattr(whispr, "get_client", Mock(return_value=client))
    assert whispr.openai_transcribe(audio, "key").text == "hello"
    assert client.audio.transcriptions.create.call_args.kwargs["file"].closed
    client.__exit__.assert_called_once()


def test_unsupported_suffix(tmp_path):
    audio = tmp_path / "audio.txt"
    audio.write_bytes(b"test")
    with pytest.raises(ValueError, match="extension"):
        whispr.openai_transcribe(audio, "key")


@pytest.mark.parametrize("failure", [None, "download", "transcribe", "oversize"])
def test_download_cleanup(monkeypatch, failure):
    monkeypatch.setattr(whispr, "validate_duration", Mock())
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [b"OggS", b"audio"]
    if failure == "download":
        response.raise_for_status.side_effect = requests.HTTPError("failed")
    if failure == "oversize":
        monkeypatch.setattr(whispr, "MAX_AUDIO_BYTES", 4)
    download = Mock(return_value=response)
    monkeypatch.setattr(whispr.requests, "get", download)
    paths = []
    original_temporary_directory = whispr.TemporaryDirectory

    def directory(**kwargs):
        result = original_temporary_directory(**kwargs)
        paths.append(Path(result.name))
        return result

    monkeypatch.setattr(whispr, "TemporaryDirectory", directory)

    def transcribe(path, key, model):
        assert path.suffix == ".ogg"
        assert path.read_bytes() == b"OggSaudio"
        if failure == "transcribe":
            raise RuntimeError("failed")
        return SimpleNamespace(text="hello")

    transcription = Mock(side_effect=transcribe)
    monkeypatch.setattr(whispr, "openai_transcribe", transcription)
    args = ("https://api.twilio.com/media/test", "key", "sid", "token")
    if failure:
        with pytest.raises((requests.HTTPError, RuntimeError, ValueError)):
            whispr.transcribe_urlmedia(*args)
    else:
        assert whispr.transcribe_urlmedia(*args) == "hello"
    assert paths and all(not path.exists() for path in paths)
    assert download.call_args.kwargs["timeout"] == (5, 15)
    assert download.call_args.kwargs["auth"] == ("sid", "token")
    response.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "url",
    [
        "http://api.twilio.com/media",
        "https://example.com/media",
        "https://api.twilio.com.evil.example/media",
        "https://user:pass@api.twilio.com/media",
    ],
)
def test_reject_untrusted_download_url(url):
    with pytest.raises(ValueError, match="Twilio API"):
        whispr.transcribe_urlmedia(url, "key", "sid", "token")
