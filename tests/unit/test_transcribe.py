import os
import tempfile
from pathlib import Path

import pytest

from wappler.speech2text.whispr import transcribe
from wappler.utils import config


class TestSpeech2Text:

    def test_load_message(self, test_audio_path):
        audio_path = Path(test_audio_path) / "human_audio_ger.m4a"
        bin_audio = open(audio_path, "rb")
        assert bin_audio is not None

    @pytest.mark.skipif(
        os.getenv("ENVIRONMENT") not in ["test", "local"],
        reason="Skipping an OpenAI API call test - wrong environment",
    )
    def test_parse_message_oaei(self, test_audio_path):
        audio_path = Path(test_audio_path) / "human_audio_ger.m4a"
        bin_audio = open(audio_path, "rb")
        with tempfile.TemporaryDirectory() as tmpdirname:
            tdir_path = Path(tmpdirname)
            with open(tdir_path / "testfile.m4a", "wb") as tmpfile:
                tmpfile.write(bin_audio.read())
            oaei_key = os.getenv("OPENAI_API_KEY")
            assert oaei_key is not None
            oaei_payload = transcribe(
                audio_file_path=str(tdir_path / "testfile.m4a"), openai_key=oaei_key
            )
            assert oaei_payload is not None
            # assert oaei_payload.text == 'Moin, ich bin Max.'
