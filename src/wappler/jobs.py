"""Small transactional job store; PostgreSQL in deployment, SQLite locally.

Admission, quotas and claims serialize in the database, across processes. No
vendor operation runs inside a transaction. A job that might have reached a
vendor is never automatically retried after an interrupted worker.
"""

import hashlib
import sqlite3
import time
import uuid
from contextlib import contextmanager

from wappler.utils.config import Settings

RETENTION_SECONDS = 7 * 86400
JOB_MAX_AGE = 900
LEASE_SECONDS = 600


class JobStore:
    """Persistent queue, sliding-window quotas, and bounded worker claims."""

    def __init__(self, settings: Settings, clock=time.time):
        self.settings = settings
        self.clock = clock
        self.postgres = not settings.database_url.startswith("sqlite:")

    @contextmanager
    def transaction(self):
        """Serialize short mutations; errors roll back and fail closed."""
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(
                self.settings.database_url,
                connect_timeout=5,
                options="-c statement_timeout=5000 -c lock_timeout=5000",
                row_factory=dict_row,
            )
        else:
            connection = sqlite3.connect(self.settings.database_url.removeprefix("sqlite:///"), timeout=5)
            connection.row_factory = sqlite3.Row
        try:
            if self.postgres:
                connection.execute("SELECT pg_advisory_xact_lock(827461)")
            else:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def execute(self, connection, sql, parameters=()):
        """Execute parameterized SQL shared by the two supported drivers."""
        return connection.execute(sql.replace("?", "%s") if self.postgres else sql, parameters)

    def now(self, connection):
        """Use database time across deployed processes; injectable time locally."""
        if self.postgres:
            return float(connection.execute("SELECT EXTRACT(EPOCH FROM clock_timestamp()) AS now").fetchone()["now"])
        return self.clock()

    def initialize(self):
        """Create the initial schema; future schema changes require migrations."""
        with self.transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, account TEXT NOT NULL, message TEXT NOT NULL,
                sender_key TEXT NOT NULL, sender TEXT NOT NULL, media_url TEXT,
                mime TEXT NOT NULL, created DOUBLE PRECISION NOT NULL,
                updated DOUBLE PRECISION NOT NULL, state TEXT NOT NULL,
                reply_sid TEXT, error TEXT, UNIQUE(account, message))""")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created)")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_sender_created ON jobs(sender_key, created)")

    def maintain(self, connection, now):
        self.execute(connection, "DELETE FROM jobs WHERE created < ?", (now - RETENTION_SECONDS,))
        self.execute(
            connection,
            """UPDATE jobs SET state='expired', sender='', media_url=NULL, mime='', updated=?
            WHERE state='queued' AND created <= ?""",
            (now, now - JOB_MAX_AGE),
        )
        self.execute(
            connection,
            """UPDATE jobs SET state='uncertain', sender='', media_url=NULL, mime='', updated=?
            WHERE state IN ('processing','transcribing','sending') AND updated <= ?""",
            (now, now - LEASE_SECONDS),
        )

    def admit(self, account, message, sender, media_url, mime):
        """Return (accepted|duplicate|limited|full|disabled, opaque job ID).

        Limits count admitted operations, including help replies and failures.
        Rejected and duplicate requests never consume another quota slot.
        """
        sender_key = hashlib.sha256(sender.encode()).hexdigest()
        with self.transaction() as connection:
            now = self.now(connection)
            self.maintain(connection, now)
            existing = self.execute(
                connection, "SELECT id FROM jobs WHERE account=? AND message=?", (account, message)
            ).fetchone()
            if existing:
                return "duplicate", existing["id"]
            if not self.settings.processing_enabled:
                return "disabled", None
            windows = [
                (3600, self.settings.sender_hourly_limit, sender_key),
                (3600, self.settings.global_hourly_limit, None),
                (86400, self.settings.global_daily_limit, None),
            ]
            for seconds, limit, key in windows:
                sql = "SELECT COUNT(*) AS n FROM jobs WHERE created > ?"
                args = (now - seconds,)
                if key:
                    sql += " AND sender_key=?"
                    args += (key,)
                if self.execute(connection, sql, args).fetchone()["n"] >= limit:
                    return "limited", None
            pending = connection.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE state IN ('queued','processing','transcribing','sending')"
            ).fetchone()["n"]
            if pending >= self.settings.max_pending_jobs:
                return "full", None
            job_id = uuid.uuid4().hex
            self.execute(
                connection,
                """INSERT INTO jobs
                (id,account,message,sender_key,sender,media_url,mime,created,updated,state)
                VALUES (?,?,?,?,?,?,?,?,?,'queued')""",
                (job_id, account, message, sender_key, sender, media_url, mime, now, now),
            )
            return "accepted", job_id

    def claim(self):
        """Claim one queued job, enforcing concurrency across all workers."""
        with self.transaction() as connection:
            now = self.now(connection)
            self.maintain(connection, now)
            if not self.settings.processing_enabled:
                return None
            active = connection.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE state IN ('processing','transcribing','sending')"
            ).fetchone()["n"]
            if active >= self.settings.worker_concurrency:
                return None
            row = connection.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created, id LIMIT 1").fetchone()
            if row is None:
                return None
            self.execute(connection, "UPDATE jobs SET state='processing',updated=? WHERE id=?", (now, row["id"]))
            return dict(row)

    def transition(self, job_id, expected, state, reply_sid=None, error=None):
        """Fence a worker whose claim has expired; clear payload on completion."""
        with self.transaction() as connection:
            now = self.now(connection)
            terminal = state in {"succeeded", "failed", "uncertain"}
            sql = "UPDATE jobs SET state=?,updated=?,reply_sid=?,error=?"
            if terminal:
                sql += ",sender='',media_url=NULL,mime=''"
            sql += " WHERE id=? AND state=? AND updated > ?"
            changed = self.execute(
                connection, sql, (state, now, reply_sid, error, job_id, expected, now - LEASE_SECONDS)
            ).rowcount
            if changed != 1:
                raise RuntimeError("Job claim expired or changed")

    def snapshot(self):
        """Return aggregate operational data without message contents."""
        with self.transaction() as connection:
            now = self.now(connection)
            self.maintain(connection, now)
            counts = {
                row["state"]: row["n"]
                for row in connection.execute("SELECT state,COUNT(*) AS n FROM jobs GROUP BY state").fetchall()
            }
            oldest = connection.execute("SELECT MIN(created) AS oldest FROM jobs WHERE state='queued'").fetchone()[
                "oldest"
            ]
            return {"jobs": counts, "oldest_queued_seconds": max(0, int(now - oldest)) if oldest is not None else 0}
