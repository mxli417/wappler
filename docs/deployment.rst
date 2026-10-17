Render deployment
=================

.. note::

   This document is retained as an engineering reference. Wappler concluded as
   a local Twilio Sandbox proof-of-concept and is not planned for deployment.
   A Render Static Site cannot safely replace this backend because provider
   credentials and Twilio webhook verification require server-side execution.

The Blueprint retains one native Python web service on plan: free. Its build
uses uv sync --frozen, pins the uv version, and starts
wappler.api:wappler_app through Uvicorn. Render checks /ready for database
availability; /heartbeat remains process liveness. No paid worker or database
is provisioned by the Blueprint.

Setup
-----

1. Review and commit the code, lock file and Blueprint. Run CI first.
2. Provision an external PostgreSQL database. A free provider tier can serve
   the pilot, subject to its availability, expiry, storage and backup limits.
   Render's own free PostgreSQL expires after 30 days and has no backups.
3. Create/update the Render Blueprint linked to the intended branch. Supply
   DATABASE_URL and the OpenAI/Twilio secrets marked sync: false in Render.
   Use the database provider's TLS connection settings. An existing service
   needs its Environment values updated manually; .env is not uploaded.
4. Set the allowlisted phone numbers and the exact public HTTPS /v0/twilio URL.
   Keep the default quotas and embedded workers enabled for this pilot.
5. Deploy manually and confirm /ready returns 200. Production startup rejects
   local SQLite and fails closed when the database cannot initialize.
6. Configure the Twilio incoming POST webhook. Test an actual phone message and
   inspect both job events and Twilio delivery status.

See :doc:`delivery` for all acceptance gates and :doc:`security` for credential
separation. No secrets are copied automatically between local development,
GitHub/GitLab and Render.

Free-tier limitations
---------------------

Free Render web services sleep after fifteen minutes without incoming traffic,
can restart, and lose their local files. PostgreSQL preserves quotas and pending
jobs independently, but embedded workers cannot process while the web service
sleeps. The first incoming webhook after sleep can time out while Render wakes.
Queued jobs over fifteen minutes old expire instead of sending a stale reply.
Use short voice notes and controlled callers for acceptance testing.

Keeping SQLite on the free web service would reset the ten-per-hour rule after
restarts. There is intentionally no silent in-memory fallback when PostgreSQL
is unavailable. Database persistence does not imply backups or high availability.

Release and rollback
---------------------

Automatic deploy remains off. After CI and real-phone acceptance pass, optionally
set autoDeployTrigger: checksPass and require checks in branch protection.
Keep a known-good commit and use Render rollback when a release fails. Preserve
the database; deleting state would remove quota and duplicate protection.

The initial schema is created idempotently at startup. Future incompatible
schema changes need an explicit migration/rollback plan; create-if-absent is
not a migration framework. Python 3.11.9 remains the existing deployment pin;
a tested Python patch upgrade is a separate delivery maintenance task.

Set PROCESSING_ENABLED=false and redeploy to stop new admissions and claims.
Already-running provider calls may finish. Investigate uncertain jobs in Twilio
before asking for a new message; do not blindly requeue them.

When always-on compute is wanted, use WORKER_ENABLED=false on the web service
and run python -m wappler.worker on a separate worker, sharing the same database
and quota configuration. Do not claim that adding more web processes increases
the global worker limit or makes the free plan always available.

References
----------

* `Blueprint specification <https://render.com/docs/blueprint-spec>`_
* `Environment variables <https://render.com/docs/configure-environment-variables>`_
* `Free-tier limits <https://render.com/docs/free>`_
* `Background workers <https://render.com/docs/background-workers>`_
* `Service metrics <https://render.com/docs/service-metrics>`_
* `Logs <https://render.com/docs/logging>`_
