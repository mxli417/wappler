import os
import tempfile
from pathlib import Path

import pytest

from wappler.speech2text.whispr import check_size, transcribe
from wappler.utils import config


class TestSpeech2Text:

    def test_load_message(self, test_audio_path):
        audio_path = Path(test_audio_path) / "human_audio_ger.m4a"
        bin_audio = open(audio_path, "rb")
        assert bin_audio is not None

    def test_check_audio_small(self, test_audio_path):
        audio_path = Path(test_audio_path) / "human_audio_ger.m4a"
        assert check_size(audio_path) == True

    def test_check_audio_large(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            tdir_path = Path(tmpdirname)
            with open(tdir_path / "too-big-too-fail.mp3", "wb") as out:
                out.truncate(1024 * 1024 * 30)
            assert check_size(tdir_path / "too-big-too-fail.mp3") == False

    @pytest.mark.skipif(
        os.getenv("ENVIRONMENT") not in ["test", "local"],
        reason="Skipping OpenAI API call test - wrong environment",
    )
    def test_parse_message_oaei(self, test_audio_path):
        audio_path = Path(test_audio_path) / "human_audio_ger.m4a"
        oaei_key = os.getenv("OPENAI_API_KEY")
        assert oaei_key is not None
        oaei_payload = transcribe(audio_file_path=audio_path, openai_key=oaei_key)
        assert oaei_payload is not None
        assert oaei_payload.text == "Moin, ich bin Max."
