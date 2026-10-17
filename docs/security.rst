Security and secret management
==============================

Scope
-----

Wappler exposes a Twilio webhook. It uses signed requests, an explicit sender
allowlist and temporary audio storage. These controls support a small live
service; they are not a guarantee against every abuse or availability failure.
Audio leaves the deployment for processing by Twilio and OpenAI.

Mapping the Flask reference to FastAPI
------------------------------------------

The
`Twilio Flask validation tutorial <https://www.twilio.com/docs/usage/tutorials/how-to-secure-your-flask-app-by-validating-incoming-twilio-requests>`_
uses the SDK validator with the account auth token, request URL, form and
signature header. Wappler already applies that validation before processing.

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Flask example
     - Wappler implementation
   * - request.form
     - Await req.form() to parse Starlette FormData.
   * - request.url
     - TWILIO_APP_URL supplies the exact public URL behind a proxy.
       The incoming URL is used only as the development fallback.
   * - RequestValidator
     - The same Twilio SDK validator, using TWILIO_TOKEN.
   * - abort(403)
     - Raise FastAPI HTTPException with status_code=403.
   * - Reusable decorator
     - Validation is inline in the one webhook route. A FastAPI dependency
       would make sense if more Twilio routes are added.
   * - Testing without validation
     - Keep validation enabled. Offline tests sign forms with a dummy token.

Flask itself and the Flask decorator are not dependencies this service needs.
No session-based CSRF layer is present, so there is no Flask CSRF setting to
copy. All submitted fields are passed to the validator, including fields
Twilio may add later; do not filter the form before validation.

Operational requirements
------------------------

Use HTTPS. Configure the identical URL in Twilio and TWILIO_APP_URL, including
scheme, hostname, path, query and encoding. Prefer a webhook URL without a query.
Do not solve proxy failures by trusting arbitrary Host or forwarded headers.

The current validator uses a configured canonical URL. If support for multiple
public URLs or query-dependent routing is added, bind validation to the actual
request path and raw query as well as the trusted external origin. Test that
a changed query or form field fails authentication. A valid signature is not
a timestamp and does not prevent replay.

Keep the auth token for the account that sends the webhook. A Twilio API key
used for outbound requests is not a substitute for that webhook signing token.
The allowlist, AccountSid and To checks are additional application controls.
See `Twilio webhook security <https://www.twilio.com/docs/usage/webhooks/webhooks-security>`_.

Implemented abuse controls
--------------------------

The webhook body is capped at 64 KiB while streaming, before form parsing, with
a ten-second read timeout. Missing signatures are rejected early. Multipart
file parts, repeated fields and more than 100 fields are rejected. The incoming
query must match the configured public URL. Interactive API docs and the old
public /stats endpoint are disabled.

The database atomically deduplicates account/message IDs and enforces at most
ten admitted operations per sender per rolling hour. Global defaults are
40/hour and 100/24 hours, a maximum of 20 pending jobs and two concurrent jobs.
Help messages and failed jobs count; duplicates do not. Rejections do not send
another paid reply. A database outage fails closed. Production requires external
PostgreSQL so a free Render restart cannot reset quotas. Deduplication lasts
seven days; it is not indefinite replay protection.

Only Twilio API HTTPS hosts and the authenticated mms.twiliocdn.com redirect
destination are allowed. Each hop is checked, and Twilio account credentials
are withheld from the CDN. The streamed audio cap is 24 MiB. Local metadata
inspection requires a positive finite duration of at most 300 seconds by
default. WebM is excluded from webhook inputs because this parser cannot
inspect its duration. Download elapsed-time checks supplement read/connect
timeouts but do not constitute a hard process deadline.

Guardrails for the model
------------------------

The model performs transcription only. Audio cannot select another model,
execute tools, modify quotas or request recursive model calls. A second LLM
or prompt-injection classifier would not enforce capacity limits reliably.
Authentication, quotas, duration/byte bounds, concurrency and a kill switch
are the relevant first guardrails. No automated paid retries are enabled.

These controls reduce abuse; they cannot promise that nobody can cause cost.
The local SDK wrapper and anyone possessing the API key can bypass webhook
quotas. Forged audio metadata can evade a metadata-only duration check. Keep
the allowlist narrow, isolate production keys, set provider usage notifications,
and use PROCESSING_ENABLED=false plus a redeploy to stop new work. Already
in-flight calls may finish. Broader public use requires stronger media isolation
and hard execution limits, with an explicit cost policy.

Remaining security and reliability work
---------------------------------------

The application does not provide edge DDoS protection. Configure hosting-level
controls when the audience grows. Verify actual Twilio CDN behavior on the
account before broadening the host allowlist. Add delivery callbacks and alerts;
API acceptance is not delivery. Validate deployment/recovery and database
backup/expiry policies. See :doc:`delivery` and ADR-002 through ADR-006 in
:doc:`decisions`. The general
`Flask security guidance <https://flask.palletsprojects.com/en/stable/web-security/>`_
also supports bounding resource use; browser session/CSRF controls do not
replace signed-webhook authentication in this FastAPI service.

Where credentials belong
------------------------

.. list-table::
   :header-rows: 1
   :widths: 25 30 45

   * - Context
     - Required values
     - Storage and access
   * - Offline tests
     - None
     - Dummy settings are injected; vendor transports are blocked.
   * - Local OpenAI test
     - OPENAI_API_KEY
     - Ignored .env or process environment, using a test key.
   * - Local Twilio test
     - Account token/SID, sender, allowlist, test recipient
     - Test account or subaccount credentials in local environment.
   * - GitHub live OpenAI job
     - OPENAI_API_KEY
     - Environment secret in openai-live; injected only into the test step.
   * - GitLab live job, if adopted
     - OPENAI_API_KEY
     - Protected, masked/hidden CI/CD variable scoped to the job environment.
   * - Render
     - Production OpenAI/Twilio settings and DATABASE_URL
     - Service Environment settings or a deliberately scoped environment group.
   * - PyPI release
     - Publisher identity
     - Prefer Trusted Publishing instead of a long-lived upload token.

Local development
-----------------

Keep .env untracked and never put credentials into fixtures. Environment
variables take precedence over .env. Do not print keys or raw vendor errors.
A shell command containing a literal key can leak through history or process
inspection; prefer editing the ignored file or a secret-injection tool.

For an installed wheel, automatic .env discovery is checkout-specific. Supply
process environment variables or explicitly load a chosen file with::

   python -m uvicorn wappler.api:wappler_app --env-file /path/to/private.env

GitHub Actions
--------------

The existing repository uses GitHub Actions, not GitLab CI/CD.

Under repository Settings, create the openai-live environment and add the
OPENAI_API_KEY secret. Configure allowed deployment branches and required
reviewers where available. The existing workflow is manual and checks that it
runs on the default branch. Normal PR checks receive no vendor credentials.

The workflow passes the secret as a step environment variable. No .env artifact
is created. Keep the live job separate from untrusted PR code; masking is not
a defense against code that deliberately reads a secret.
See `GitHub Actions secrets <https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets>`_.

GitLab CI/CD, if you move hosting
--------------------------------------

GitLab uses pipelines and jobs defined in .gitlab-ci.yml; none is included here.
Add OPENAI_API_KEY under Settings > CI/CD > Variables as a regular variable,
mark it masked/hidden and protected, and scope it to a dedicated test environment.

A manually triggered job on a protected default branch should declare that
environment and run the same pytest --live -m openai_live command. Keep live
secrets unavailable to merge-request/fork jobs. A GitLab file-type variable
contains a temporary file path, not the API key value, so do not use that type
for OPENAI_API_KEY without adding explicit file loading.
See `GitLab CI/CD variables <https://docs.gitlab.com/ci/variables/>`_.

Render
------

Store production values in the Render service's Environment settings. The
Blueprint contains names and sync: false, not secret values. That flag prompts
for values during initial Blueprint creation; existing services need manual
updates. It does not fetch GitHub/GitLab secrets or the developer's .env.

Use an environment group only when the services should intentionally share the
same credentials. Environment variables are sufficient for the current app;
Render Secret Files are not required. Restrict dashboard access, update values
there during rotation, and redeploy to ensure the running process uses them.
See `Render secrets <https://render.com/docs/configure-environment-variables>`_
and the `Blueprint reference <https://render.com/docs/blueprint-spec#prompting-for-secret-values>`_.

Separation and rotation
-----------------------

Use different OpenAI keys for local/CI testing and production, preferably with
separate project access and spending controls. Use a Twilio test account or
subaccount with its own sender for real message tests; fake unit-test values
cannot send real WhatsApp messages.

Rotate any credentials previously printed by the prototype or exposed in a
repository. Keep starlette_formdata.txt out of commits and distribution archives:
it is an unused captured webhook containing message/account metadata.

Job database privacy
--------------------

Queued jobs retain the recipient and media URL required for processing. Terminal
transitions/expiry clear that payload. IDs, sender digest, timestamps, state and
error class remain for seven days; cleanup runs only while the app is active.
No transcript or audio is stored in the database. Digests are pseudonymous, not
anonymous. Protect DATABASE_URL, database access and backups accordingly.
