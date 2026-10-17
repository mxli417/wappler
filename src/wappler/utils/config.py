"""Lazy runtime configuration; importing modules needs no credentials."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


def get_project_root() -> Path:
    """Return the repository root in a src-layout checkout."""
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    """Application settings with secrets excluded from their representation."""

    openai_api_key: str = field(repr=False)
    twilio_token: str = field(repr=False)
    twilio_sid: str
    whatsapp_from: str
    allowed_senders: tuple[str, ...]
    webhook_url: str = ""
    environment: str = "dev"
    database_url: str = field(default="sqlite:///wappler.db", repr=False)
    sender_hourly_limit: int = 10
    global_hourly_limit: int = 40
    global_daily_limit: int = 100
    max_pending_jobs: int = 20
    worker_concurrency: int = 2
    worker_enabled: bool = True
    processing_enabled: bool = True
    max_audio_seconds: int = 300

    @classmethod
    def from_env(cls) -> "Settings":
        """Load checkout .env values without overriding environment variables.

        TWILIO_TEST_MSG_FROM and ENVIRONMENT_CONFIG remain legacy fallbacks.
        """
        load_dotenv(get_project_root() / ".env", override=False)
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            twilio_token=os.getenv("TWILIO_TOKEN", ""),
            twilio_sid=os.getenv("TWILIO_SID", ""),
            whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM") or os.getenv("TWILIO_TEST_MSG_FROM", ""),
            allowed_senders=tuple(s.strip() for s in os.getenv("ALLOWED_WHATSAPP_SENDERS", "").split(",") if s.strip()),
            webhook_url=os.getenv("TWILIO_APP_URL", ""),
            environment=os.getenv("ENVIRONMENT") or os.getenv("ENVIRONMENT_CONFIG", "dev"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///wappler.db"),
            sender_hourly_limit=int(os.getenv("SENDER_HOURLY_LIMIT", "10")),
            global_hourly_limit=int(os.getenv("GLOBAL_HOURLY_LIMIT", "40")),
            global_daily_limit=int(os.getenv("GLOBAL_DAILY_LIMIT", "100")),
            max_pending_jobs=int(os.getenv("MAX_PENDING_JOBS", "20")),
            worker_concurrency=int(os.getenv("WORKER_CONCURRENCY", "2")),
            worker_enabled=os.getenv("WORKER_ENABLED", "true").lower() == "true",
            processing_enabled=os.getenv("PROCESSING_ENABLED", "true").lower() == "true",
            max_audio_seconds=int(os.getenv("MAX_AUDIO_SECONDS", "300")),
        )

    def validate(self) -> None:
        """Reject missing or malformed settings without exposing their values.

        Raises:
            ValueError: Required settings are absent or invalid.
        """
        required = {
            "OPENAI_API_KEY": self.openai_api_key,
            "TWILIO_TOKEN": self.twilio_token,
            "TWILIO_SID": self.twilio_sid,
            "TWILIO_WHATSAPP_FROM": self.whatsapp_from,
            "ALLOWED_WHATSAPP_SENDERS": self.allowed_senders,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("Missing settings: " + ", ".join(missing))
        for number in (self.whatsapp_from, *self.allowed_senders):
            if not number.startswith("whatsapp:+") or not number[10:].isdigit():
                raise ValueError("WhatsApp numbers must use whatsapp:+ followed by digits")
        if self.webhook_url:
            url = urlsplit(self.webhook_url)
            if (
                url.scheme != "https"
                or not url.netloc
                or url.path != "/v0/twilio"
                or url.fragment
                or url.username
                or url.password
            ):
                raise ValueError("TWILIO_APP_URL must be the public HTTPS /v0/twilio URL")
        elif self.environment == "production":
            raise ValueError("TWILIO_APP_URL is required in production")
        if not 1 <= self.sender_hourly_limit <= 10:
            raise ValueError("SENDER_HOURLY_LIMIT must be between 1 and 10")
        for name in ("global_hourly_limit", "global_daily_limit", "max_pending_jobs", "max_audio_seconds"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if not 1 <= self.worker_concurrency <= 4:
            raise ValueError("WORKER_CONCURRENCY must be between 1 and 4")
        if not self.database_url.startswith(("sqlite:///", "postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")
        if self.environment == "production" and self.database_url.startswith("sqlite:"):
            raise ValueError("Production requires PostgreSQL to preserve quotas across free-tier restarts")
