"""Offline integration across the webhook and real wrappers, mocking HTTP edges."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from wappler import worker
from wappler.speech2text import whispr
from wappler.wappchat import pchat


def test_voice_note_to_reply(signed_post, form, monkeypatch, drain, test_audio_path):
    monkeypatch.setattr(worker, "transcribe_urlmedia", whispr.transcribe_urlmedia)
    monkeypatch.setattr(worker, "create_wapp_msg", pchat.create_wapp_msg)
    download = MagicMock()
    download.__enter__.return_value = download
    download.iter_content.return_value = [(test_audio_path / "human_audio_ger.ogg").read_bytes()]
    monkeypatch.setattr(whispr.requests, "get", Mock(return_value=download))
    openai_client = MagicMock()
    openai_client.__enter__.return_value = openai_client
    openai_client.audio.transcriptions.create.return_value = SimpleNamespace(text="Moin, ich bin Max.")
    monkeypatch.setattr(whispr, "get_client", Mock(return_value=openai_client))
    twilio = Mock()
    twilio.messages.create.return_value.sid = "SMreply"
    monkeypatch.setattr(pchat, "Client", Mock(return_value=twilio))
    assert signed_post(form).status_code == 200
    drain()
    assert twilio.messages.create.call_args.kwargs["body"] == "Hey, I understood: Moin, ich bin Max."
    assert openai_client.audio.transcriptions.create.call_args.kwargs["file"].closed
