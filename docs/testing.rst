Testing and documentation
=========================

Offline checks
--------------

Run from the repository root::

   uv sync --frozen --extra dev
   uv run --frozen --extra dev pytest
   uv run --frozen --extra dev black src tests docs/conf.py --check
   uv run --frozen --extra dev isort src tests docs/conf.py --check-only
   uv run --frozen --extra dev flake8 src tests docs/conf.py --select=E9,F63,F7,F82
   uv run --frozen --extra dev sphinx-build -W --keep-going -b html docs docs/_build/html

Alternatively, run the configured environments with uv run tox.
Open docs/_build/html/index.html after the documentation build.

Sphinx uses autodoc, Napoleon for Google-style docstrings, and viewcode.
Public Python APIs are included by module in api.rst. Add documentation there
when introducing modules. Importing the application for autodoc loads no
credentials and makes no vendor requests.

The default pytest run uses injected settings and mocked vendor boundaries.
HTTP transports used by Requests, HTTPX, and the OpenAI SDK's HTTPX2 transport
are blocked in offline tests. A regression test checks the SDK's default
transport cannot bypass this guard.
Coverage includes signatures behind a proxy, authorization, response statuses,
audio limits, temporary-file cleanup, configuration, and upstream failures.

The webhook integration test crosses the real webhook and wrapper functions with
mocked transport responses. It admits and drains a job, downloads the checked-in
OGG fixture and checks its duration. It verifies data flow and cleanup, not
speech recognition accuracy.

Local transcription tests
-------------------------

Use two layers before calling a paid endpoint::

   uv run --frozen --extra dev pytest tests/unit/test_transcribe.py tests/unit/test_audio_fixture.py
   uv run --frozen --extra dev pytest tests/integration/test_openai_contract.py

The unit tests verify size and format checks, file/client cleanup, timeouts,
download failures and URL restrictions. The contract tests use the real OpenAI
SDK with a mock HTTP transport: they inspect the multipart upload, original
audio bytes, filename and model, parse the SDK response, and simulate HTTP
401/429/500 plus read timeouts. They make no external requests.

Neither layer proves the model recognized speech. That needs the live tests.

Recorded fixtures
-----------------

human_audio_ger.m4a is a real, decodable 70,769-byte AAC recording: 3.989 seconds,
48 kHz, mono. FFmpeg measured a mean level of -31.3 dBFS and a peak of -15.3 dBFS.
It is quiet, but not empty or silent. The confirmed reference phrase is
"Moin, ich bin Max." Live OpenAI checks on 2026-10-03 returned exactly that text
for both the M4A and OGG fixtures using whisper-1.

human_audio_ger.ogg is an Opus version of the same recording, generated with::

   ffmpeg -i tests/assets/audio/human_audio_ger.m4a -c:a libopus -b:a 32k tests/assets/audio/human_audio_ger.ogg

This covers the common WhatsApp container/codec combination but is not a capture
of an actual inbound WhatsApp message. Keep the original M4A unchanged.

The audio fixture tests decode both files with FFmpeg and check duration and RMS
level. They skip if FFmpeg is unavailable locally. Linux CI installs FFmpeg and
sets REQUIRE_AUDIO_CHECK=1 so missing decoding support fails that check.
FFmpeg is a test tool only; the application sends original audio directly.

Live tests
----------

For OpenAI integration only, set OPENAI_API_KEY in .env or the environment and run::

   uv run --frozen --extra dev pytest --live -m openai_live tests/integration/test_live.py -v

This makes two paid transcription calls, one per fixture, with whisper-1. It
needs no Twilio credentials and sends no WhatsApp messages. The tests require
exactly the words "moin ich bin max", allowing only punctuation and case changes.
Use -rP to show the successful fixture transcripts. Vendor failures are reported
without raw API exception text that might expose account details. For a larger
corpus, add word-error-rate thresholds and language,
noise and duration cases rather than exact punctuation comparisons.

To explicitly test real WhatsApp sending instead::

   uv run --frozen --extra dev pytest --live -m twilio_live tests/integration/test_live.py -v

Set the required credentials and TWILIO_TEST_MSG_TO. The recipient must be in
ALLOWED_WHATSAPP_SENDERS. Ensure Twilio permits the intended outbound message,
for example by sending an inbound message from your phone first.

The outbound test checks acceptance by Twilio, not phone delivery. Neither
test is a complete incoming WhatsApp test. Running with --live -m live enables
both providers; select openai_live when you only want transcription.

Manual acceptance
-----------------

Before using a deployment, verify:

* A short real WhatsApp voice note produces one readable reply.
* Plain text and an image produce a useful instruction.
* A non-allowlisted sender cannot trigger transcription.
* A voice note over the configured duration is rejected before OpenAI upload.
* Duplicate webhooks and the eleventh operation cannot trigger extra paid work.
* Queued jobs survive redeploys; interrupted in-flight jobs become uncertain.
* Twilio reports successful reply delivery.
* No secrets or message contents appear in application logs.

Continuous integration
----------------------

The Checks workflow runs on pushes, pull requests, manual dispatch and a weekly
schedule. It uses current official checkout, setup-python and upload-artifact
actions pinned to immutable commit IDs. Jobs are:

* Offline tests on Windows and Linux with at least 90% coverage; Linux also
  requires the real audio fixtures to decode successfully.
* PostgreSQL contract tests against a disposable Linux service container: quota
  races, duplicate races, restart state, claims, expiry and retention.
* Formatting, focused Flake8 error checks, distribution build and Sphinx with
  warnings treated as errors. HTML documentation and distributions are artifacts.
* pip-audit against the frozen installed dependencies, including development
  tools. Only the local editable project is excluded from advisory lookup.

Normal CI has no live API credentials and does not publish or deploy. The
separate OpenAI transcription smoke test workflow is manual, runs only for
the repository default branch and selects openai_live. Configure a GitHub
environment named openai-live with OPENAI_API_KEY and, if desired, required
reviewers and default-branch restrictions. No Twilio secret is needed.

Dependabot checks GitHub Actions and uv dependencies weekly. Review its changes
and ensure the requirements files and uv.lock stay synchronized. Require the
offline test jobs, quality job and dependency audit before merging. After a
successful Render smoke test, Render can deploy on passing checks.

Dependency maintenance
----------------------

The October 2026 refresh updates FastAPI/Starlette, OpenAI, Twilio, dotenv,
Pydantic and development tools. Unused bumpversion and the old direct Pydantic
development pin were removed. Sphinx 9.0.4 is retained as the newest release
compatible with Python 3.11; Sphinx 9.1 requires Python 3.12.

uv.lock records exact versions. Use uv sync --frozen --extra dev for repeatable
checks. When intentionally updating dependencies, run uv sync --upgrade
--extra dev, repeat the offline checks, and audit advisories::

   uv run --frozen --extra dev pip-audit --skip-editable

The audit needs network access to the advisory service; it uses no vendor API
credentials. The live OpenAI smoke test remains a separate opt-in check after
an SDK update.

Queue and worker tests
----------------------

The default offline run uses a temporary SQLite database per test. PostgreSQL
cases skip unless TEST_DATABASE_URL is set. To exercise the real driver and
locking locally, start a disposable PostgreSQL container::

   docker run --detach --rm --name wappler-test-postgres --publish 127.0.0.1:55432:5432 --env POSTGRES_PASSWORD=wappler-local-test --env POSTGRES_DB=wappler_test postgres:17-alpine

In PowerShell::

   $env:TEST_DATABASE_URL = "postgresql://postgres:wappler-local-test@127.0.0.1:55432/wappler_test"
   uv run --frozen --extra dev pytest tests/unit/test_jobs.py -v
   Remove-Item Env:TEST_DATABASE_URL
   docker stop wappler-test-postgres

These are dummy local credentials, not secrets to reuse in deployment. The test
fixture requires localhost and database name wappler_test, and deletes rows
from its jobs table between cases. Never point it at a real service database.
The same cases run against SQLite and PostgreSQL. Worker lifecycle tests use
real threads but mocked providers, including a blocked transcription to prove
that webhook acknowledgement does not wait for provider completion.

The duration check uses metadata, not full decoding. Existing real-fixture
decoding tests complement it but do not prove resistance to arbitrary malformed
audio. The pure OpenAI live test bypasses webhook quota controls by design.
