import os
import tempfile
from pathlib import Path

import pytest

from wappler.speech2text.whispr import transcribe
from wappler.utils import config


class End2End:

    @pytest.mark.skipif(
        os.getenv("ENVIRONMENT") not in ["test", "local"],
        reason="Skipping an OpenAI API call test - wrong environment",
    )
    def test_init(self, test_audio_path):
        pass

    @pytest.mark.skipif(
        os.getenv("ENVIRONMENT") not in ["test", "local"],
        reason="Skipping an OpenAI API call test - wrong environment",
    )
    def test_runthrough(self, test_audio_path):
        pass
