"""Bounded media downloads and OpenAI transcription without local conversion."""

import math
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin, urlsplit

import mutagen
import requests
from openai import OpenAI
from openai.types.audio import Transcription

MAX_AUDIO_BYTES = 24 * 1024 * 1024
MEDIA_SUFFIXES = {
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
}
SUPPORTED_SUFFIXES = {".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".wav", ".webm"}


def check_size(filepath: str | Path) -> bool:
    """Return whether a file is nonempty and at most 24 MiB."""
    return 0 < Path(filepath).stat().st_size <= MAX_AUDIO_BYTES


def get_client(openai_key: str) -> OpenAI:
    """Create a client with a finite timeout and no automatic retries.

    The caller must close the client. Retries are disabled because the current
    worker must not repeat a potentially billed request on an ambiguous failure.
    """
    return OpenAI(api_key=openai_key, timeout=30.0, max_retries=0)


def openai_transcribe(audio_file_path: str | Path, openai_key: str, oai_model: str = "whisper-1") -> Transcription:
    """Transcribe a supported local audio file.

    Args:
        audio_file_path: File with an extension identifying its audio container.
        openai_key: API key used only for this request.
        oai_model: Transcription model; defaults to the existing Whisper model.

    Returns:
        The SDK transcription object, whose text contains the transcript.

    Raises:
        ValueError: File is empty, oversized, or has an unsupported suffix.
        OSError: File cannot be read.
        openai.APIError: Upstream transcription fails.
    """
    path = Path(audio_file_path)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("Unsupported audio file extension")
    if not check_size(path):
        raise ValueError("Audio must be nonempty and at most 24 MiB")
    with path.open("rb") as audio, get_client(openai_key) as client:
        return client.audio.transcriptions.create(model=oai_model, file=audio)


def transcribe_urlmedia(
    media_url: str,
    openai_key: str,
    twilio_sid: str,
    twilio_token: str,
    oai_model: str = "whisper-1",
    media_content_type: str = "audio/ogg",
    max_audio_seconds: int = 300,
) -> str:
    """Download Twilio audio into temporary storage and return its transcript.

    Only Twilio API hosts and the documented authenticated CDN are accepted.
    Redirects are checked individually; credentials never go to the CDN.
    Duration metadata is checked before uploading. Files are always removed.

    Args:
        media_url: Media URL from an authenticated Twilio webhook.
        openai_key: OpenAI API key.
        twilio_sid: Twilio account SID for media authentication.
        twilio_token: Twilio account auth token.
        oai_model: OpenAI transcription model.
        media_content_type: MIME type supplied by the signed webhook.

    Returns:
        Transcribed text.

    Raises:
        ValueError: URL, content type, or file size is invalid.
        requests.RequestException: Download fails.
        openai.APIError: Transcription fails.
    """
    validate_media_url(media_url)
    mime = media_content_type.split(";", 1)[0].strip().lower()
    if mime not in MEDIA_SUFFIXES:
        raise ValueError("Unsupported audio content type")
    with TemporaryDirectory(prefix="wappler-") as directory:
        path = Path(directory) / ("audio" + MEDIA_SUFFIXES[mime])
        download_audio(media_url, path, twilio_sid, twilio_token)
        validate_duration(path, max_audio_seconds)
        return openai_transcribe(path, openai_key, oai_model).text


def validate_media_url(media_url: str, allow_cdn: bool = False) -> None:
    """Reject non-HTTPS URLs and hosts outside the Twilio media boundary."""
    url = urlsplit(media_url)
    host = url.hostname or ""
    if (
        url.scheme != "https"
        or not (
            host == "api.twilio.com"
            or (host.startswith("api.") and host.endswith(".twilio.com"))
            or (allow_cdn and host == "mms.twiliocdn.com")
        )
        or url.username
        or url.password
        or url.port not in (None, 443)
    ):
        raise ValueError("Expected a Twilio API HTTPS media URL")


def validate_duration(path: Path, maximum: int) -> None:
    """Check local duration metadata before any paid transcription.

    This is a cost guard, not proof against deliberately falsified metadata.
    WebM is excluded from webhook formats because this parser cannot inspect it.
    """
    try:
        audio = mutagen.File(path)
        duration = audio.info.length if audio is not None else 0
        if not math.isfinite(duration) or not 0 < duration <= maximum:
            raise ValueError("Audio duration is outside the allowed range")
    except Exception:
        raise ValueError("Audio duration is unreadable or exceeds the limit") from None


def download_audio(media_url: str, path: Path, twilio_sid: str, twilio_token: str) -> None:
    """Stream at most 24 MiB, with at most three validated redirects.

    Elapsed-time checks run between chunks; a stalled read may add one read
    timeout. This is not a hard process execution deadline.
    """
    started = time.monotonic()
    for _ in range(4):
        validate_media_url(media_url, allow_cdn=True)
        auth = None if urlsplit(media_url).hostname == "mms.twiliocdn.com" else (twilio_sid, twilio_token)
        with requests.get(media_url, auth=auth, stream=True, timeout=(5, 15), allow_redirects=False) as response:
            if time.monotonic() - started > 45:
                raise ValueError("Download deadline exceeded")
            if response.status_code in (301, 302, 303, 307, 308):
                media_url = urljoin(media_url, response.headers.get("Location", ""))
                continue
            response.raise_for_status()
            size = 0
            with path.open("wb") as audio:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if time.monotonic() - started > 45:
                        raise ValueError("Download deadline exceeded")
                    size += len(chunk)
                    if size > MAX_AUDIO_BYTES:
                        raise ValueError("Audio exceeds 24 MiB")
                    audio.write(chunk)
            return
    raise ValueError("Too many media redirects")
