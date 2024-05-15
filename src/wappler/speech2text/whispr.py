"""OpenAI API wrapper functions for speech 2 text"""

import os
from pathlib import Path
from typing import Dict, Union

from openai import OpenAI

from wappler.utils.logger import get_logger

logger = get_logger(__name__)


def check_size(filepath: str) -> bool:
    """Checks if audio file size is larger than 24 MB - reject if larger

    Args:
        filepath (str): path to (temporary) audio file

    Returns:
        bool: True if audio file size is smaller or equal than 24 MB, else False
    """
    fsize = os.stat(filepath)
    mb_size = int(fsize.st_size / 1024 / 1024)
    if mb_size > 24:
        logger.error(
            "File size of (fpath)%s is too large: (mb_size)%s" % (filepath, mb_size)
        )
        return False
    else:
        logger.info("File size of (fpath)%s is: (mb_size)%s" % (filepath, mb_size))
        return True


def get_client(openai_key: str) -> OpenAI:
    """Instantiates an OpenAI api client with a given OpenAI key

    Args:
        openai_key (str): OpenAI API key

    Returns:
        OpenAI: client for further communication with the OpenAI API
    """
    return OpenAI(api_key=openai_key)


def transcribe(
    audio_file_path: Union[str, Path], openai_key: str, oai_model: str = "whisper-1"
) -> Dict:
    """Transcription wrapper function for passing on audio to the OpenAI api for speech 2 text models
    Supports multi-language transcription with a max audio file size of XXX MB

    Args:
        audio_file_path (Union[str, Path]): path to a (temporary) audio file
        openai_key (str): OpenAI API key
        oai_model (str, optional): OpenAI API model. Defaults to "whisper-1".

    Returns:
        Dict: OpenAI API return json-like object
    """
    supported_ftypes = [".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"]
    if Path(audio_file_path).suffix not in supported_ftypes:
        logger.error("Audio file type not supported: %s" % Path(audio_file_path).suffix)
    if not check_size(audio_file_path):
        logger.error(
            "Aborting transferring of audio file: %s" % str(Path(audio_file_path))
        )
        return None
    bin_audio = open(audio_file_path, "rb")
    client = get_client(openai_key=openai_key)
    if client is None:
        logger.error("OpenAI api client init failed: %s" % client)
        return None
    transcription = client.audio.transcriptions.create(
        model=oai_model,
        file=bin_audio,
    )
    return transcription
