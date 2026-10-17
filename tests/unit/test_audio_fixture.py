"""Decode recorded fixtures to distinguish real samples from empty containers."""

import array
import math
import os
import shutil
import subprocess
import sys

import pytest


@pytest.mark.audio_fixture
@pytest.mark.parametrize("filename", ["human_audio_ger.m4a", "human_audio_ger.ogg"])
def test_recording_is_decodable_and_not_silent(test_audio_path, filename):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        if os.getenv("REQUIRE_AUDIO_CHECK") == "1":
            pytest.fail("FFmpeg is required for the audio fixture check")
        pytest.skip("Install FFmpeg to decode the audio fixture locally")
    result = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(test_audio_path / filename),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    samples = array.array("h")
    samples.frombytes(result.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    duration = len(samples) / 16000
    assert 3.5 < duration < 4.5, f"Unexpected duration: {duration:.2f}s"
    rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples)) / 32768
    assert rms > 0.001, "Recording is silent or below -60 dBFS RMS"
