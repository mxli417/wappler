Architecture decision records
=============================

These records describe the current code and the delivery decisions made during
the October 2026 repair. They distinguish implementation from a verified hosted
deployment. Changes to an accepted decision should add a superseding record,
preserving its context and consequences. See :doc:`delivery` for release gates.

ADR-001: Keep a standalone transcription service
------------------------------------------------

:Date: 2026-10-03
:Status: Accepted; implemented
:Context: The prototype had broken dependency/configuration paths, inconsistent
          HTTP responses and insufficient isolation for local tests.
:Decision: Use a small FastAPI app factory, typed settings loaded at startup,
           Twilio for WhatsApp, and OpenAI whisper-1 for transcription. Keep
           network adapters separate from HTTP admission and job storage.
           Upload original audio; do not host a model or convert audio locally.
:Alternatives: Meta's direct API, a local model, or a general conversational
               assistant would substantially expand setup and scope.
:Consequences: This remains a standalone deployment, but audio is processed by
               two external providers. It cannot read personal WhatsApp chats.
               There are provider charges and independent data-retention rules.
:Verification: Mocked SDK contracts and fixture tests; the earlier live OpenAI
               test returned "Moin, ich bin Max." for both M4A and OGG fixtures.
               Actual inbound WhatsApp delivery remains a deployment gate.

ADR-002: Authenticate and bound the webhook before admission
------------------------------------------------------------

:Date: 2026-10-03
:Status: Accepted; implemented
:Context: A public endpoint can be flooded before its signature is checked.
          A valid signature alone does not authorize every sender or stop replay.
:Decision: Cap streamed form bodies at 64 KiB with a ten-second body-read timeout.
           Reject missing signatures early, uploaded files, repeated fields and
           more than 100 fields. Validate all remaining fields with Twilio's SDK
           against the canonical public URL; also bind the incoming query.
           Enforce sender, account and destination checks before job admission.
           Disable public interactive API docs and the old statistics route.
:Alternatives: Trusting source IPs, arbitrary forwarded headers, or a secret URL
               would provide weaker authentication. Flask-specific decorators,
               session cookies and CSRF middleware do not fit this service.
:Consequences: Unexpected webhook schema changes fail closed and may need review.
               The application does not supply network-level DDoS protection.
               Browser CSP/session settings from Flask's security guidance are
               not a substitute for webhook controls.
:Verification: Signed/tampered forms, duplicate fields, oversized chunked bodies,
               authorization failures and proxy/query cases have offline tests.

ADR-003: Put deterministic limits before paid model work
--------------------------------------------------------

:Date: 2026-10-03
:Status: Accepted; implemented, with a documented metadata limitation
:Context: An allowlisted account can still spam transcription or become
          compromised. A byte limit alone does not limit audio duration.
:Decision: Admit at most ten operations per sender in any rolling 3,600 seconds.
           The setting may be lowered, never raised above ten. Defaults also
           cap all senders at 40 operations per rolling hour and 100 per rolling
           24 hours, with 20 pending jobs and two concurrent workers. Help replies
           and failed jobs consume admission quota; duplicate IDs do not.
           PROCESSING_ENABLED=false stops new admissions and worker claims.
           Keep the 24 MiB streamed media cap; check a default maximum duration
           of 300 seconds locally with Mutagen before the OpenAI upload.
:Alternatives: A second LLM acting as a guard would add latency and cost without
               reliably enforcing numeric limits. Content moderation would not
               solve capacity abuse. This service has no tools, chat history,
               model selection or instructions controlled by incoming audio.
:Consequences: Quota rejection returns 429 without sending another paid reply.
               Slots are consumed when work is accepted, not refunded on failure.
               These are operation limits, not a guaranteed dollar ceiling.
               Duration metadata can be inaccurate or deliberately forged; the
               parser is not a sandbox or a complete audio validator. WebM is no
               longer accepted by the webhook because its duration cannot be
               inspected with this parser. Direct local SDK calls are outside
               the web service's admission/duration controls.
:Verification: Both database backends run the same quota/concurrency contract.
               Real M4A/OGG fixtures pass duration inspection. Overlong, invalid
               and non-finite duration values are rejected. Before opening the
               allowlist broadly, evaluate isolated decoding and hard execution
               limits against malformed media, and configure vendor usage alerts.

ADR-004: Persist jobs and quotas together; retain free Render compute
---------------------------------------------------------------------

:Date: 2026-10-03
:Status: Implemented; external database provisioning and hosted checks pending
:Context: Free Render web-service storage disappears on restart, redeploy and
          spin-down. In-memory or local SQLite limits cannot enforce a persistent
          ten-per-hour rule. A separate Render background worker has no free tier.
:Decision: Keep render.yaml plan: free. Use external PostgreSQL for production
           queue state, admission quotas and duplicate protection. Use SQLite
           for local development only; production startup rejects it. Persist
           admission and quota reservation in one transaction, then return
           empty TwiML immediately. Run two embedded worker threads in the
           free web process. A separate python -m wappler.worker entry point
           permits splitting compute later without changing the queue contract.
:Alternatives: Celery plus a persistent Redis-compatible broker is established,
               but adds another datastore for this small workload. A background
               task without external state would lose accepted work. A paid
               always-on worker conflicts with the requested pilot cost limit.
:Consequences: Database transactions serialize admission and claims. PostgreSQL
               uses an advisory transaction lock and database time; SQLite uses
               BEGIN IMMEDIATE. This intentionally favors correctness at a small
               workload over maximum throughput. The app owns a small queue
               implementation that requires maintenance and failure tests.
               No DB transaction remains open during a provider call.
               The web process can sleep: queued jobs survive but cannot run
               until it wakes. Queue acceptance is not a timely-delivery promise.
               No database account, paid resource or deployment is created by
               this change. A database URL must be supplied separately.
:Verification: Concurrent admissions, duplicate races, restart persistence,
               global worker capacity, expiry and failed transactions are tested.
               A real PostgreSQL CI service checks driver/locking behavior.

PostgreSQL storage is required for the current hosted configuration. A free
database provider tier can be used for the pilot, subject to its own limits.
Render's own free PostgreSQL expires after 30 days and has no backups; it is
not a permanent storage commitment. Production startup fails closed when the
database is unavailable instead of resetting quotas into memory.

ADR-005: Prefer a missed reply over an automatic duplicate charge
-----------------------------------------------------------------

:Date: 2026-10-03
:Status: Accepted for the controlled pilot; operator recovery remains manual
:Context: A remote transcription/send can succeed even when its response is
          lost. Automatically reclaiming and retrying such work can double bill
          or send duplicate WhatsApp replies.
:Decision: Deduplicate account/message IDs for seven days. Jobs move through
           queued, processing, transcribing and sending to succeeded, failed or
           uncertain. Persist the outbound SID on success. Disable automatic
           OpenAI retries and make one worker attempt per admitted job. Mark
           stale in-flight jobs uncertain after ten minutes; never reclaim them
           automatically. Expire queued jobs after fifteen minutes. A stale
           worker must pass a conditional state update before its next stage.
:Alternatives: At-least-once retries improve completion rates but need explicit
               accounting and reconciliation of external effects. Exactly-once
               delivery cannot be guaranteed by a database transaction spanning
               independent provider APIs.
:Consequences: An interrupted accepted message may never produce a reply. A
               duplicate webhook still receives 200 for an existing failed or
               uncertain job. Sender/media URL payload is cleared at terminal
               transitions; expired/stale payloads are cleared by maintenance.
               No audio or transcripts are stored in the job database. SID,
               pseudonymous sender digest, timestamps and error class remain
               until seven-day retention cleanup. A digest is not anonymization.
               Deduplication no longer covers messages after that retention.
               Cleanup runs while the app is active, not while Render sleeps.
:Verification: Tests cover interrupted jobs, stale-worker fencing, payload
               cleanup, expiry, replay after success/failure and ambiguous send
               failures. A kill/redeploy test on the actual deployment remains
               part of delivery acceptance.

ADR-006: Use Render logs and service metrics first
--------------------------------------------------

:Date: 2026-10-03
:Status: Application telemetry implemented; hosted alert setup pending
:Context: The old /stats counter counted reply characters in one process and
          could not reveal failed transcription or blocked jobs.
:Decision: Emit structured JSON admission/job events with opaque job IDs, stage,
           duration and error class. Emit queue state counts and oldest queued
           age periodically while workers run. Use /heartbeat for liveness and
           /ready for a database availability check. Render checks /ready.
           Use Render's log search and resource metrics for the pilot.
:Alternatives: ELK adds indexing, retention, access control and maintenance that
               this workload does not yet justify. A public metrics endpoint
               would not by itself establish monitoring or alerting.
:Consequences: Logs exclude audio, transcript, phone number, media URL and secret
               values. Job failure and queue-age alerts still need configuring
               in the hosting/observability accounts. Readiness does not prove
               that OpenAI or Twilio is working or that a reply was delivered.
               No paid vendor health probe runs on the public endpoints.
:Verification: Failure tests inspect safe responses and job state. Hosted log
               visibility, alert delivery and retention are deployment checks.

ADR-007: Separate offline CI, paid tests and deployment secrets
---------------------------------------------------------------

:Date: 2026-10-03
:Status: Workflow files implemented; remote check/secret configuration pending
:Context: Tests previously depended on incorrect imports and environmental
          assumptions. A normal PR must not consume paid APIs or read secrets.
:Decision: Lock dependencies with uv; include dynamic requirements files in uv's
           cache keys. Run offline tests on Windows/Linux, coverage, formatting,
           targeted static checks, package and Sphinx builds, and an advisory
           audit. Pin GitHub Actions to commit IDs. Exercise PostgreSQL in a
           separate Linux CI service using dummy credentials. Keep live OpenAI
           tests manual and confined to an environment on the default branch.
           Keep automatic Render deployments off until the pilot passes.
:Alternatives: Running live tests on every PR increases cost and secret exposure.
               A GitLab pipeline is possible but this repository uses GitHub;
               maintaining two CI systems adds unnecessary work now.
:Consequences: Local .env, GitHub environment secrets and Render Environment
               settings are separate stores. DATABASE_URL joins the production
               secret set. CI uses no real OpenAI/Twilio/database credentials.
               A dependency audit does not establish absence of vulnerabilities.
:Verification: Local checks exercise the workflow commands. A successful local
               run is not evidence that GitHub branch protection or a Render
               deployment has already been configured.

ADR-008: Publish documentation with code; gate package release separately
-------------------------------------------------------------------------

:Date: 2026-10-03
:Status: Documentation/package preparation implemented; publication deferred
:Context: A README must explain the actual service, limits, setup and ownership.
          Sphinx/API docs and an architecture description should remain usable
          without credentials. Publishing to PyPI is distinct from hosting.
:Decision: Maintain README, Sphinx autodoc, architecture, security, deployment,
           testing, these ADRs and the delivery checklist together. Build wheel
           and source archives in CI; exclude secrets, captures and local state.
           Keep TestPyPI/PyPI release as a separate optional milestone.
:Alternatives: Publishing immediately would skip name/version, fixture rights,
               installed-package and publisher-identity checks.
:Consequences: The checked-in LICENSE contains GPLv3, not MIT. Earlier metadata
               and documentation describing MIT were incorrect. Metadata now
               says GPL-3.0-only to match the supplied version; the license text
               itself is unchanged. Owner review of licensing intent, source
               provenance and voice-fixture redistribution remains a release
               gate. The package has not been uploaded or reserved on PyPI.
:Verification: Sphinx warnings are errors; distribution metadata and contents
               are checked. Prefer Trusted Publishing for a future release.

References and review triggers
------------------------------

* `Render free limits <https://render.com/docs/free>`_: revisit ADR-004 if cold
  starts, database expiry or sleep prevent acceptable pilot behavior.
* `Render workers <https://render.com/docs/background-workers>`_: split workers
  from the web process when an always-on deployment is authorized.
* `Render metrics <https://render.com/docs/service-metrics>`_ and
  `logs <https://render.com/docs/logging>`_: add external telemetry when retention
  or alerting needs exceed the chosen plan.
* `PostgreSQL locking <https://www.postgresql.org/docs/current/explicit-locking.html>`_:
  replace the serialized claim design if measured contention warrants it.
* `Twilio webhook security <https://www.twilio.com/docs/usage/webhooks/webhooks-security>`_
  and `Flask security guidance <https://flask.palletsprojects.com/en/stable/web-security/>`_:
  reassess authentication/input limits when routes or callers expand.
* `Twilio authenticated media <https://help.twilio.com/articles/223183748-How-to-protect-media-access-with-HTTP-basic-authentication-for-Programmable-Messaging>`_:
  only documented API hosts and mms.twiliocdn.com may be followed. Add a new
  host only after verifying a legitimate account flow; never allow all S3 hosts.
* `Mutagen duration metadata <https://mutagen.readthedocs.io/en/latest/index.html>`_:
  revisit isolated decoding before handling arbitrary public uploads.
