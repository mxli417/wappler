"""Exercise real worker lifecycle without provider traffic."""

import threading
from dataclasses import replace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from wappler import worker
from wappler.api import create_app
from wappler.jobs import JobStore


def test_embedded_workers_process_persisted_jobs(settings, vendors):
    store = JobStore(settings)
    store.initialize()
    store.admit(settings.twilio_sid, "SMqueued", settings.allowed_senders[0], None, "")
    completed = threading.Event()
    original_transition = store.transition

    def transition(*args, **kwargs):
        result = original_transition(*args, **kwargs)
        if args[2] == "succeeded":
            completed.set()
        return result

    store.transition = transition
    workers = worker.Workers(store)
    workers.start()
    try:
        assert completed.wait(5), "Persisted queued job was not processed"
        assert store.snapshot()["jobs"] == {"succeeded": 1}
        vendors[1].assert_called_once()
    finally:
        workers.stop()
    assert all(not thread.is_alive() for thread in workers.threads)


def test_app_acknowledges_before_blocked_provider_finishes(settings, vendors, form):
    entered, release = threading.Event(), threading.Event()

    def transcribe(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return "hello"

    vendors[0].side_effect = transcribe
    with TestClient(create_app(replace(settings, worker_enabled=True))) as client:
        signature = RequestValidator(settings.twilio_token).compute_signature(settings.webhook_url, form)
        try:
            response = client.post("/v0/twilio", data=form, headers={"X-Twilio-Signature": signature})
            assert response.status_code == 200
            assert entered.wait(5)
            vendors[1].assert_not_called()
        finally:
            release.set()


def test_worker_storage_failure_is_sanitized_and_stops(settings, monkeypatch):
    store = JobStore(settings)
    workers = worker.Workers(store)
    events = []

    def broken_claim():
        workers.stopping.set()
        workers.wakeup.set()
        raise RuntimeError("private database password")

    monkeypatch.setattr(store, "claim", broken_claim)
    monkeypatch.setattr(worker, "event", lambda name, **values: events.append((name, values)))
    workers.run()
    assert events == [("worker_store_unavailable", {"error": "RuntimeError"})]


def test_job_state_write_failure_does_not_retry_vendor(settings, vendors, monkeypatch):
    store = JobStore(settings)
    store.initialize()
    store.admit("ACtest", "SMtest", settings.allowed_senders[0], None, "")
    job = store.claim()
    monkeypatch.setattr(store, "transition", Mock(side_effect=RuntimeError("private database password")))
    events = []
    monkeypatch.setattr(worker, "event", lambda name, **values: events.append((name, values)))
    worker.process_job(store, job)
    vendors[1].assert_not_called()
    assert events[0][0] == "job_state_write_failed"
    assert "private" not in str(events)


def test_standalone_worker_can_stop_without_vendor_calls(settings, monkeypatch):
    monkeypatch.setattr(worker.Settings, "from_env", lambda: settings)

    def interrupt(_):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", interrupt)
    worker.main()
