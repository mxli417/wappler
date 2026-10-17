"""Bounded database-backed workers, embedded for the free-tier pilot."""

import json
import threading
import time

from wappler.jobs import JobStore
from wappler.speech2text.whispr import transcribe_urlmedia
from wappler.utils.config import Settings
from wappler.utils.log import get_logger
from wappler.wappchat.pchat import create_wapp_msg

logger = get_logger(__name__)


def event(name, **fields):
    """Log only explicitly supplied, non-content operational fields."""
    logger.info(json.dumps({"event": name, **fields}, sort_keys=True))


def process_job(store: JobStore, job: dict):
    """Attempt a job once; never blindly repeat an ambiguous vendor call."""
    settings = store.settings
    started = time.monotonic()
    stage = "processing"
    job_id = job["id"]
    try:
        if job["media_url"]:
            # Record potential paid work before entering any vendor call.
            store.transition(job_id, stage, "transcribing")
            stage = "transcribing"
            transcript = transcribe_urlmedia(
                job["media_url"],
                settings.openai_api_key,
                settings.twilio_sid,
                settings.twilio_token,
                media_content_type=job["mime"],
                max_audio_seconds=settings.max_audio_seconds,
            )
            body = "Hey, I understood: " + transcript
            if len(body) > 1500:
                body = body[:1450] + "\n[Transcript shortened]"
        else:
            body = "Please send one supported audio attachment to transcribe."
        store.transition(job_id, stage, "sending")
        stage = "sending"
        reply_sid = create_wapp_msg(
            account_sid=settings.twilio_sid,
            auth_token=settings.twilio_token,
            msg_from=settings.whatsapp_from,
            msg_to=job["sender"],
            msg_body=body,
        )
        store.transition(job_id, stage, "succeeded", reply_sid=reply_sid)
        event("job_succeeded", job_id=job_id, duration_ms=int((time.monotonic() - started) * 1000))
    except Exception as exc:
        # Sending may have succeeded remotely even when the response was lost.
        outcome = "uncertain" if stage == "sending" else "failed"
        try:
            store.transition(job_id, stage, outcome, error=type(exc).__name__)
        except Exception:
            event("job_state_write_failed", job_id=job_id)
        event(
            "job_failed",
            job_id=job_id,
            stage=stage,
            error=type(exc).__name__,
            outcome=outcome,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


class Workers:
    """Poll persistent jobs with fixed concurrency and interruptible idle waits."""

    def __init__(self, store: JobStore):
        self.store = store
        self.stopping = threading.Event()
        self.wakeup = threading.Event()
        self.threads = []

    def start(self):
        for index in range(self.store.settings.worker_concurrency):
            thread = threading.Thread(target=self.run, name=f"wappler-worker-{index}", daemon=True)
            self.threads.append(thread)
            thread.start()

    def notify(self):
        self.wakeup.set()

    def run(self):
        last_report = 0
        while not self.stopping.is_set():
            try:
                if threading.current_thread().name.endswith("-0") and time.monotonic() - last_report >= 60:
                    event("queue_health", **self.store.snapshot())
                    last_report = time.monotonic()
                job = self.store.claim()
                if job:
                    process_job(self.store, job)
                    continue
            except Exception as exc:
                event("worker_store_unavailable", error=type(exc).__name__)
            self.wakeup.wait(10)
            self.wakeup.clear()

    def stop(self):
        self.stopping.set()
        self.wakeup.set()
        deadline = time.monotonic() + 20
        for thread in self.threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))


def main():
    """Run a separate worker when moving beyond the free web-service pilot."""
    settings = Settings.from_env()
    settings.validate()
    store = JobStore(settings)
    store.initialize()
    workers = Workers(store)
    workers.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        workers.stop()


if __name__ == "__main__":
    main()
