Delivery plan and acceptance gates
==================================

.. note::

   This is a historical plan. The project concluded after a successful local
   Twilio Sandbox demonstration on 17 October 2026. Production WABA,
   deployment, and operational acceptance gates are intentionally not being
   pursued.

Target: a working, controlled WhatsApp transcription pilot on Render's free
web service. This does not require buying always-on compute or publishing to
PyPI. Completed code is distinct from configured accounts and observed delivery.

1. Review and verify the implementation
---------------------------------------

Implemented in the working tree:

* Runtime/configuration repair, dependency lock, original-container transcription,
  offline and explicit live tests, README and Sphinx documentation.
* Signed bounded webhooks, allowlist, account/destination checks, checked media
  redirects, byte/duration guards and safe application logging.
* Transactional jobs, seven-day duplicate protection, rolling sender/global
  quotas, a bounded queue, worker concurrency and a processing kill switch.
* JSON job events, queue summaries, liveness/readiness and a free Render Blueprint.
* GitHub offline/quality/audit checks, PostgreSQL contract checks, manual OpenAI
  smoke testing and Dependabot. Architecture decisions are in :doc:`decisions`.

Before merging: run the commands in :doc:`testing`, inspect the full diff, review
the changed asynchronous HTTP semantics and ensure all GitHub checks pass.
Set required checks/branch protection in GitHub; workflow files do not do this.
Keep the live OpenAI workflow secret in its dedicated environment. Normal CI
uses no provider secrets. Earlier live fixture tests passed; do not interpret
that as a deployed WhatsApp acceptance test.

2. Provision persistent state and configure the pilot
-----------------------------------------------------

The owner supplies a PostgreSQL database and stores DATABASE_URL in Render
Environment settings. Use TLS according to the provider's connection guidance.
Use a database dedicated to this service and restrict dashboard/database access.
Do not put the URL in the Blueprint, a commit or a public build artifact.

The Render web service remains free. A free database tier is possible; Render's
free PostgreSQL currently expires after 30 days and has no backups. Record its
expiry date and a migration/stop reminder. The Blueprint does not provision a
database or any paid resource automatically. The alternative of local SQLite
on free Render would reset quotas and lose jobs, so production rejects it.

Configure the OpenAI/Twilio settings, sender allowlist and exact public HTTPS
webhook URL. Retain the default limits (10/sender/hour, 40/global/hour,
100/global/day, 20 pending jobs, 2 workers, 300 seconds per audio).
Set usage notifications in provider accounts. These notifications may be soft
alerts; do not assume they impose a hard dollar cap. To stop new work, set
PROCESSING_ENABLED=false and redeploy. Calls already in flight can finish.

Exit gate: secrets supplied, database initialized, /ready returns 200, free plan
confirmed, no credentials or message bodies in logs, automatic deploy still off.

3. Demonstrate real WhatsApp behavior
-------------------------------------

Owner/maintainer acceptance checks:

1. Send a short voice note from an allowed phone; receive one accurate reply.
   Inspect the matching job event and Twilio delivery status. An API-accepted
   send is not proof that the phone received it.
2. Send the known phrase "Moin, ich bin Max." and verify the four words.
3. Confirm an unlisted sender triggers no OpenAI call or outbound help reply.
4. Replay a test webhook: it must not create another job or paid call. Use dummy
   vendor adapters locally for repeated/rate-limit testing, not ten paid calls
   merely to exercise the limiter.
5. Confirm text/image help is also quota-controlled. Oversized or overlong media
   must not reach OpenAI; examine the job failure event.
6. Let Render sleep and try again. Record actual cold-start behavior and Twilio
   errors. Do not use synthetic keep-alive traffic to disguise the free-tier
   limitation. A first webhook can fail during cold start.
7. Redeploy with a queued job and confirm persisted state remains. Interrupt a
   test worker during processing: expect uncertain state and no automatic resend.
8. Temporarily break a test database connection: admission/readiness must fail
   closed, then recover without clearing counters.

Exit gate: the actual phone workflow is demonstrated, no unexplained duplicate
charge/reply, and free-tier delay/failure behavior is explicitly accepted.
Jobs waiting over fifteen minutes expire; they are not delivered hours later.

4. Make pilot operations reviewable
-----------------------------------

Configure Render log access and notifications for deploy/availability failures.
Verify that job_failed, job_state_write_failed, worker_store_unavailable and
queue_health events are visible. Configure job-error and oldest-queue-age alerts
with available account tooling; logging alone does not configure those alerts.
Test alert delivery. Document who reviews failed/uncertain jobs.

Recovery: for an uncertain send, inspect Twilio before asking the user to resend
as a new message. Do not set an uncertain row back to queued blindly. Failed
transcriptions may also have consumed vendor usage. Keep PostgreSQL state when
rolling back code; reverting the application must not reset the hourly limits.

Exit gate: an operator can identify failures, disable new processing, check an
ambiguous send, roll back code and preserve quotas. Backups/retention depend on
the selected database provider and must be checked explicitly.

5. Declare the controlled pilot delivered
-----------------------------------------

Record the deployed commit, configuration names (no values), database provider
and expiry policy, successful phone test, known limitations and rollback steps.
The pilot is complete only after gates 1-4, not merely after local tests pass.
Automatic deployment may then be enabled with checksPass if desired.

Later: dependable unattended operation
--------------------------------------

If the pilot is kept live, revisit ADR-004: move to always-on web/worker compute,
disable embedded workers with WORKER_ENABLED=false on the web process, and run
python -m wappler.worker separately against the same database and quota settings.
Add delivery callbacks, provider-error classification, carefully reconciled
bounded retries, tested database backups, schema migrations and stronger media
isolation/hard execution limits. Load-test using mocked providers before sizing
workers. Add external log/metric aggregation only when actual needs justify it.

Optional independent milestone: PyPI
------------------------------------

Resolve license intent and fixture redistribution, verify the package name and
version, inspect fresh artifacts and test an isolated wheel. Then use TestPyPI
and a protected Trusted Publishing release workflow. See :doc:`packaging`.
Package publication is not required to finish the Render pilot.
