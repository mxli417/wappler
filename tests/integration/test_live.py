"""Explicitly opt-in smoke tests; these incur charges and can send messages."""

import os
import re

import pytest
from openai import APIError

from wappler.speech2text.whispr import openai_transcribe
from wappler.utils.config import Settings
from wappler.wappchat.pchat import create_wapp_msg

pytestmark = pytest.mark.live


@pytest.mark.openai_live
@pytest.mark.parametrize("filename", ["human_audio_ger.m4a", "human_audio_ger.ogg"])
def test_live_transcription(test_audio_path, filename):
    """Require all four reference words, tolerating only case and punctuation."""
    settings = Settings.from_env()
    assert settings.openai_api_key, "Set OPENAI_API_KEY before enabling live tests"
    try:
        transcript = openai_transcribe(test_audio_path / filename, settings.openai_api_key)
    except APIError as exc:
        # Vendor exception text can contain account/key details. Keep CI output safe.
        pytest.fail(
            f"OpenAI transcription failed: {type(exc).__name__} (HTTP {getattr(exc, 'status_code', 'n/a')})",
            pytrace=False,
        )
    words = re.findall(r"\w+", transcript.text.casefold())
    print(f"{filename}: {transcript.text}")  # Public test fixture only, never incoming user audio.
    assert words == ["moin", "ich", "bin", "max"], f"Unexpected transcript for {filename}: {transcript.text!r}"


@pytest.mark.twilio_live
def test_live_whatsapp_send():
    settings = Settings.from_env()
    settings.validate()
    recipient = os.getenv("TWILIO_TEST_MSG_TO", "")
    assert recipient in settings.allowed_senders, "Live recipient must be explicitly allowlisted"
    sid = create_wapp_msg(
        settings.twilio_sid,
        settings.twilio_token,
        settings.whatsapp_from,
        recipient,
        "Wappler live test: outbound messaging works.",
    )
    assert sid.startswith("SM")
