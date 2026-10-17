Architecture
============

Scope
-----

Wappler is a Python ASGI application using FastAPI. Twilio owns WhatsApp
connectivity and media hosting; OpenAI performs speech recognition. There is
no local model, conversational agent or direct Meta Cloud API integration.
The design decisions and remaining delivery gates are in :doc:`decisions`
and :doc:`delivery`.

Request and job flow
--------------------

.. code-block:: text

   WhatsApp phone -> Twilio -> signed POST /v0/twilio
                                  |
                         bounded form + authentication
                                  |
                         account / sender / media checks
                                  |
                       transactional database admission
                       deduplicate + quota + queue limit
                                  |
                       persist queued job, commit
                                  |
                       immediate HTTP 200 <Response/>

   embedded worker threads -> claim a queued job, commit
                                  |
                         download and inspect audio
                                  |
                         OpenAI whisper-1 transcription
                                  |
                         Twilio REST reply submission
                                  |
                         persist status and outbound SID

One transaction owns both quota reservation and job insertion, avoiding a
database/queue dual-write gap. PostgreSQL admission/claims serialize under a
transaction advisory lock; SQLite uses BEGIN IMMEDIATE. Database time governs
deployed rolling windows. Provider calls never hold that lock.

The free Render web process runs two embedded workers by default. Concurrency
is also enforced in shared database state. Multiple processes must use identical
quota/concurrency settings. The worker entry point permits a later split into
web and worker services; use WORKER_ENABLED=false in the web process then.

PostgreSQL is required for production. SQLite is a local development convenience
and must live on a local filesystem, not a shared network mount. Neither a
local file nor an in-memory limiter survives free Render redeploys. The queue
is persistent when PostgreSQL is persistent; worker availability still depends
on the sleeping free web process.

Modules
-------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Module
     - Responsibility
   * - wappler.api
     - App lifespan, bounded signed HTTP admission, liveness/readiness.
   * - wappler.jobs
     - Atomic quotas, duplicate detection, queue, claims and retention.
   * - wappler.worker
     - Bounded workers, stage transitions, provider orchestration and events.
   * - wappler.utils.config
     - Lazy environment loading, secret-safe settings and startup validation.
   * - wappler.speech2text.whispr
     - Checked media download, size/duration inspection and transcription.
   * - wappler.wappchat.pchat
     - Twilio reply submission and client cleanup.
   * - wappler.run
     - Optional server entry point respecting PORT.

Limits and failure semantics
----------------------------

Each admitted operation consumes a sender/global quota slot, even if it later
fails or only sends a help reply. A duplicate account/message ID consumes no new
slot and gets HTTP 200. New operations beyond a quota receive 429; full/disabled
processing or unavailable storage receives 503. Authentication and malformed
input fail before admission. HTTP 200 now means a stored job, not a sent reply.

The queue defaults to 20 pending jobs, with two active jobs globally. Sender
quota is at most ten per rolling hour. Defaults for all senders together are
40 per rolling hour and 100 per rolling 24 hours. These limit admitted jobs,
not completion timestamps, individual API-account use elsewhere or dollars.
Settings are trusted operator inputs; request parameters cannot override them.

Jobs transition through queued, processing, transcribing and sending. Terminal
states are succeeded, failed, uncertain and expired. No paid request is
automatically retried. A send timeout is uncertain because Twilio may have
accepted it. In-flight jobs with no transition for ten minutes become uncertain;
they are not requeued. Workers must pass a conditional state update before the
next stage. Jobs waiting fifteen minutes expire. These conservative rules limit
duplicate charges but can leave an accepted message without a reply.

Audio and data lifetime
-----------------------

Webhook audio formats are OGG, MP3, M4A/MP4, WAV and FLAC. WebM is excluded from
this path because Mutagen cannot inspect its duration. The standalone local
OpenAI wrapper remains reusable, outside webhook admission controls.

Initial media URLs must be HTTPS on a Twilio API host. Each redirect is checked,
with at most three redirects and only the authenticated mms.twiliocdn.com CDN
allowed in addition. Account credentials are not sent to the CDN. Downloads
have connect/read timeouts, a streamed 24 MiB limit and an elapsed-time check.
The elapsed check runs between reads; it is not a hard process deadline.
Mutagen rejects unreadable or overlong duration metadata before upload, with
a 300-second default. This does not fully validate hostile audio or guarantee
duration when container metadata is deliberately falsified.

Original audio is sent directly to OpenAI. Temporary directories are cleaned
on ordinary success/failure; abrupt process termination cannot run cleanup.
Render's ephemeral filesystem is not an audio archive. No audio or transcript
is intentionally persisted in PostgreSQL. While pending, the database stores
sender and media URL so a worker can process the job. Terminal transitions and
expiry clear these payload fields. IDs, sender digest, timestamps, status and
error class are retained for seven days; maintenance runs only while the app
is active. Digests remain potentially identifying. Provider retention is
governed separately by Twilio and OpenAI.

Replies are capped at 1500 characters. Multi-message replies, transcript
archives and delivery-status callbacks are not implemented. Outbound SID
storage proves provider acceptance, not delivery to the phone.

Operations and scaling
----------------------

/heartbeat reports process liveness; /ready checks database access. Public
/stats and interactive API documentation are removed. JSON events describe
admission, outcome, stage, elapsed processing time and aggregate queue health.
The queue snapshot shows oldest waiting age and counts over retained jobs.

The current serialized queue targets a small allowlisted service, not high
throughput. Measure before changing it. For unattended operation, separate an
always-on worker, establish backups and migrations, add delivery callbacks and
carefully reconciled retry policies, and test crash/redeploy behavior. A
dedicated broker or SKIP LOCKED worker design can be evaluated when measured
database contention or scheduling needs justify the extra complexity.
