Getting started
===============

Install
-------

Use Python 3.11 and uv from the repository root::

   uv sync --extra dev

The repository lock file records the tested dependency set. For a reproducible
installation, use::

   uv sync --frozen --extra dev

Configure
---------

Copy .env-template to .env only if you do not already have a .env file.
Merge the new settings into an existing file instead of overwriting credentials.
Environment variables take precedence over the checkout-local .env file.

.. list-table:: Environment variables
   :header-rows: 1
   :widths: 35 65

   * - Variable
     - Purpose
   * - OPENAI_API_KEY
     - API key with access to transcription.
   * - TWILIO_SID
     - Account SID that owns the WhatsApp sender.
   * - TWILIO_TOKEN
     - Auth token for that account, also used for webhook signatures.
   * - TWILIO_WHATSAPP_FROM
     - Registered sender or Sandbox number, with whatsapp:+ prefix.
   * - ALLOWED_WHATSAPP_SENDERS
     - Comma-separated caller numbers, each with whatsapp:+ prefix.
       Required; an empty list prevents startup.
   * - TWILIO_APP_URL
     - Exact public HTTPS webhook URL, including /v0/twilio and any query.
       Required when ENVIRONMENT is production.
   * - ENVIRONMENT
     - dev by default; use production on Render.
   * - DATABASE_URL
     - sqlite:///wappler.db locally; external PostgreSQL required in production.
       Treat the URL as a secret. See deployment for free-tier considerations.
   * - TWILIO_TEST_MSG_TO
     - Recipient for the opt-in live messaging test only.
   * - PORT
     - Port used by python -m wappler.run; defaults to 8000.

TWILIO_TEST_MSG_FROM remains a fallback for TWILIO_WHATSAPP_FROM.
ENVIRONMENT_CONFIG remains a fallback for ENVIRONMENT. New names take precedence.
Settings are loaded and validated at application startup, not module import.

Run and connect a full Twilio account
-------------------------------------

Start the development server::

   uv run uvicorn wappler.api:wappler_app --reload --port 8000

Visit http://localhost:8000/heartbeat. Expect a JSON object with status "ok".
Expose port 8000 through an HTTPS tunnel, then set TWILIO_APP_URL to its exact
/v0/twilio endpoint and restart the app.

In Twilio, configure the incoming-message webhook for your WhatsApp sender
(or its Messaging Service, depending on how inbound routing is configured)
to that URL using POST. A paid account still needs a registered, usable
WhatsApp sender. Confirm the webhook account and sender match your settings.

Send a short voice note from an allowlisted phone. You should receive a text
reply beginning "Hey, I understood:". Plain text or unsupported media gets
a short instruction to send audio. Multiple attachments are not transcribed.

For a Sandbox, join from the test phone first. See the
`Twilio WhatsApp quickstart <https://www.twilio.com/docs/whatsapp/quickstart>`_.

Troubleshooting
---------------

* Startup failure: the error names missing settings without printing secrets.
* HTTP 403: check auth token, exact public URL, allowlist, AccountSid and To.
  Do not disable signature validation to work around a proxy mismatch.
* HTTP 400: check required fields and media count.
* HTTP 415: the webhook must use form data.
* HTTP 413: the webhook body exceeds 64 KiB; this is distinct from downloaded audio.
* HTTP 429: a rolling sender or global operation quota was reached. No paid reply
  is sent for rejection; duplicates of previously admitted IDs still get 200.
* HTTP 503: storage unavailable, queue full or processing disabled.
* HTTP 200 acknowledges a persisted job, not completion. Inspect job_succeeded,
  job_failed and queue_health logs. Provider failures occur after acknowledgement.
* A successful Twilio send means acceptance, not delivery. Check Twilio delivery
  status if the reply never arrives.

The earlier prototype printed Twilio tokens. Rotate any token that was retained
in shared logs, and remove old audio files manually if an earlier run left them
in the project directory.
