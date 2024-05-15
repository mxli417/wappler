from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def test_assets_path() -> Path:
    fpath = Path(__file__).parent.resolve()
    return fpath / "assets"


@pytest.fixture(scope="session")
def test_audio_path() -> Path:
    fpath = Path(__file__).parent.resolve()
    return fpath / "assets" / "audio"
