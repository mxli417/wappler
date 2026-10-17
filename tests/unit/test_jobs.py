"""Transactional queue contract, shared by SQLite and optional local PostgreSQL."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import urlsplit

import pytest

from wappler.jobs import JOB_MAX_AGE, LEASE_SECONDS, RETENTION_SECONDS, JobStore


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, settings):
    if request.param == "postgres":
        url = os.getenv("TEST_DATABASE_URL")
        if not url:
            pytest.skip("Set TEST_DATABASE_URL to a disposable local PostgreSQL database")
        parsed = urlsplit(url)
        if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.path != "/wappler_test":
            pytest.fail("Database tests require localhost database wappler_test")
        settings = replace(settings, database_url=url)
    result = JobStore(settings)
    result.initialize()
    with result.transaction() as connection:
        connection.execute("DELETE FROM jobs")
    return result


def admit(store, message="SM1", sender="whatsapp:+15550000002"):
    return store.admit("ACtest", message, sender, "https://api.twilio.com/media/test", "audio/ogg")


def age(store, seconds):
    with store.transaction() as connection:
        store.execute(connection, "UPDATE jobs SET created=created-?, updated=updated-?", (seconds, seconds))


def test_exact_sender_limit_and_window_reopens(store):
    for number in range(10):
        assert admit(store, str(number))[0] == "accepted"
    assert admit(store, "11")[0] == "limited"
    assert admit(store, "0")[0] == "duplicate"
    assert admit(store, "other", "whatsapp:+15550000003")[0] == "accepted"
    age(store, 3601)
    assert admit(store, "11")[0] == "accepted"


def test_concurrent_admission_never_exceeds_ten(store):
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda n: admit(store, str(n))[0], range(24)))
    assert results.count("accepted") == 10
    assert results.count("limited") == 14


def test_concurrent_replay_creates_one_job(store):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: admit(store)[0], range(12)))
    assert results.count("accepted") == 1
    assert results.count("duplicate") == 11


@pytest.mark.parametrize("limit", ["global_hourly_limit", "global_daily_limit"])
def test_global_quota_across_senders(store, limit):
    store.settings = replace(store.settings, **{limit: 1})
    assert admit(store)[0] == "accepted"
    assert admit(store, "SM2", "whatsapp:+15550000003")[0] == "limited"
    age(store, 86401)
    assert admit(store, "SM2", "whatsapp:+15550000003")[0] == "accepted"


def test_full_queue_and_kill_switch(store):
    store.settings = replace(store.settings, max_pending_jobs=1)
    assert admit(store)[0] == "accepted"
    assert admit(store, "SM2")[0] == "full"
    store.settings = replace(store.settings, processing_enabled=False)
    assert admit(store, "SM2")[0] == "disabled"
    assert store.claim() is None
    assert admit(store)[0] == "duplicate"


def test_restart_preserves_queue_and_limits(store):
    admit(store)
    restarted = JobStore(store.settings)
    restarted.initialize()
    assert admit(restarted)[0] == "duplicate"
    job = restarted.claim()
    assert job["message"] == "SM1"
    assert restarted.claim() is None


def test_global_worker_capacity_and_fenced_transition(store):
    for number in range(3):
        admit(store, str(number))
    first, second = store.claim(), store.claim()
    assert first and second
    assert store.claim() is None
    store.transition(first["id"], "processing", "succeeded", reply_sid="SMreply")
    assert store.claim()
    with pytest.raises(RuntimeError, match="claim"):
        store.transition(first["id"], "processing", "sending")


def test_stale_work_is_uncertain_and_never_retried(store):
    admit(store)
    job = store.claim()
    age(store, LEASE_SECONDS + 1)
    assert store.claim() is None
    assert store.snapshot()["jobs"] == {"uncertain": 1}
    with pytest.raises(RuntimeError):
        store.transition(job["id"], "processing", "sending")
    assert admit(store)[0] == "duplicate"


def test_queue_expiry_retention_and_payload_cleanup(store):
    admit(store)
    age(store, JOB_MAX_AGE + 1)
    assert store.claim() is None
    assert store.snapshot()["jobs"] == {"expired": 1}
    with store.transaction() as connection:
        row = connection.execute("SELECT sender,media_url FROM jobs").fetchone()
        assert row["sender"] == "" and row["media_url"] is None
    age(store, RETENTION_SECONDS)
    assert store.snapshot()["jobs"] == {}


def test_terminal_state_retains_quota_and_dedup_without_payload(store):
    _, job_id = admit(store)
    store.claim()
    store.transition(job_id, "processing", "failed", error="ValueError")
    assert admit(store)[0] == "duplicate"
    with store.transaction() as connection:
        row = connection.execute("SELECT * FROM jobs").fetchone()
        assert row["sender"] == "" and row["media_url"] is None
        assert row["error"] == "ValueError"
    store.settings = replace(store.settings, sender_hourly_limit=1)
    assert admit(store, "SM2")[0] == "limited"
