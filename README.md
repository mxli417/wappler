![Wappler](https://raw.githubusercontent.com/mxli417/wappler/HEAD/assets/dalle-wappler.png)

# Wappler

Wappler is a completed proof-of-concept for transcribing WhatsApp voice notes.
It receives an authenticated Twilio WhatsApp webhook, queues the attached audio,
transcribes it, and sends the text back through Twilio.

> **Project status: concluded.** The full Twilio Sandbox flow was demonstrated
> successfully on 17 October 2026 using ngrok and a local Wappler instance. This
> repository is retained as a learning project and implementation reference. It
> is not an active service, and there are no plans to register a production
> WhatsApp Business Account (WABA), publish the package, or operate the Render
> deployment.

```text
phone -> Twilio WhatsApp Sandbox -> ngrok -> Wappler -> transcription API
  ^                                                |
  +---------------- Twilio text reply -------------+
```

## What was completed

- A FastAPI webhook with Twilio signature verification.
- Explicit sender, account, and destination checks.
- A bounded, database-backed job queue with workers and duplicate suppression.
- Per-sender and global quotas, media size and duration limits, and a processing
  kill switch.
- Temporary-file cleanup and restricted Twilio media downloads.
- SQLite support for local demonstrations and PostgreSQL support for a hosted
  pilot.
- Offline tests, mocked OpenAI SDK contract tests, real audio fixtures, Sphinx
  documentation, packaging checks, and GitHub Actions.
- A successful end-to-end Sandbox demonstration from a real WhatsApp phone.

The project deliberately stops before production WABA registration, delivery
monitoring, durable operations, and an always-on deployment.

## Why this is not a frontend-only application

A static frontend can provide recording and user-interface code, but it cannot
safely contain an OpenAI API key or Twilio Auth Token. This project also needs a
public server endpoint to verify and receive Twilio's signed webhook requests.
Consequently, a Render Static Site cannot replace the Wappler backend.

A future local-first phone application is a different and cleaner product: it
can record audio and run an on-device speech model without Twilio, ngrok, a
public webhook, or server-held credentials.

## Reproduce the Sandbox demo

This is optional. Running the offline test suite requires no provider account;
running the complete demo uses Twilio and OpenAI and may incur provider charges.

### 1. Install the project

Use Python 3.11 and [uv](https://docs.astral.sh/uv/):

```powershell
git clone https://github.com/mxli417/wappler.git
cd wappler
uv sync --frozen --extra dev
```

Copy `.env-template` to `.env`. Never commit `.env`.

```powershell
Copy-Item .env-template .env
```

Configure the following values:

| Variable | Value |
| --- | --- |
| `OPENAI_API_KEY` | An API key with transcription access |
| `TWILIO_SID` | The Account SID that owns the Sandbox |
| `TWILIO_TOKEN` | The Auth Token for that account |
| `TWILIO_WHATSAPP_FROM` | The Twilio Sandbox number, prefixed with `whatsapp:+` |
| `ALLOWED_WHATSAPP_SENDERS` | The personal phone that joined the Sandbox, prefixed with `whatsapp:+` |
| `TWILIO_TEST_MSG_TO` | The same personal phone; used only by the optional outbound test |
| `TWILIO_APP_URL` | The exact ngrok HTTPS URL plus `/v0/twilio` |
| `ENVIRONMENT` | `dev` |
| `DATABASE_URL` | `sqlite:///wappler.db` |

The number mapping is important:

```dotenv
TWILIO_WHATSAPP_FROM="whatsapp:+<Twilio Sandbox number>"
ALLOWED_WHATSAPP_SENDERS="whatsapp:+<your joined phone number>"
TWILIO_TEST_MSG_TO="whatsapp:+<your joined phone number>"
```

`TWILIO_TEST_MSG_FROM` is only a legacy fallback for
`TWILIO_WHATSAPP_FROM`; new configurations should not use it.

### 2. Join the Twilio Sandbox

In Twilio, open the WhatsApp testing/Sandbox page. Send the displayed
`join <sandbox-code>` message from the personal phone you placed in
`ALLOWED_WHATSAPP_SENDERS`. Use the Sandbox number shown in the Console as
`TWILIO_WHATSAPP_FROM`.

### 3. Expose the local server

Install ngrok, authenticate its CLI, and expose port 8000:

```powershell
ngrok config add-authtoken "<your ngrok authtoken>"
ngrok http 8000
```

If ngrok reports this public URL:

```text
https://example.ngrok-free.app
```

set the following exact value in `.env`:

```dotenv
TWILIO_APP_URL="https://example.ngrok-free.app/v0/twilio"
```

In the Twilio Sandbox configuration, set **When a message comes in** to the
same URL, select **POST**, and save. The URLs must match exactly because they
are part of Twilio's signature calculation. If the ngrok hostname changes,
update Twilio and `.env`, then restart Wappler.

### 4. Start Wappler

In a second PowerShell window:

```powershell
uv run --frozen uvicorn wappler.api:wappler_app --reload --port 8000
```

Check the service:

```powershell
Invoke-RestMethod http://localhost:8000/heartbeat
Invoke-RestMethod http://localhost:8000/ready
```

Both requests should return a successful status. Send a short voice note from
the joined and allowlisted phone to the Sandbox number. Wappler acknowledges
the webhook after persisting the job, then sends the transcript asynchronously.

The ngrok request inspector is available at `http://127.0.0.1:4040`. A webhook
`403` normally means the exact public URL, Twilio token, account, Sandbox
number, or sender allowlist does not match.

## Testing without external calls

The default suite blocks external network transports and injects dummy
credentials:

```powershell
uv run --frozen --extra dev pytest
uv run --frozen --extra dev black src tests docs/conf.py --check
uv run --frozen --extra dev isort src tests docs/conf.py --check-only
uv run --frozen --extra dev flake8 src tests docs/conf.py --select=E9,F63,F7,F82
uv run --frozen --extra dev sphinx-build -W --keep-going -b html docs docs/_build/html
```

The final local verification completed with 94 passing tests and 14 intentional
skips. The skips cover opt-in live-provider, FFmpeg-dependent, and external
PostgreSQL cases.

An explicitly enabled transcription smoke test makes two real API calls and
sends no WhatsApp messages:

```powershell
uv run --frozen --extra dev pytest --live -m openai_live tests/integration/test_live.py -v -rP
```

The outbound Twilio test sends a real message:

```powershell
uv run --frozen --extra dev pytest --live -m twilio_live tests/integration/test_live.py -v
```

## Security and shutdown checklist

Before publishing or archiving a fork:

1. Confirm `.env` is ignored with `git check-ignore .env`.
2. Inspect staged files with `git diff --cached --name-only` and never stage
   credentials, provider responses, database files, or private recordings.
3. Enable [GitHub secret scanning and push protection](https://docs.github.com/en/code-security/how-tos/secure-your-secrets/detect-secret-leaks/enable-secret-scanning)
   in **Settings -> Advanced Security** when the repository/account supports
   them.
4. Keep GitHub Actions permissions read-only unless a workflow demonstrably
   needs more access. The included workflows use `contents: read` and pinned
   action revisions.
5. After the demonstration, remove the Twilio webhook, stop ngrok, remove any
   unused GitHub Actions secrets, and delete or rotate provider credentials that
   are no longer needed.
6. Treat the checked-in audio fixtures as published data. Do not add private
   voice notes as test fixtures.

If a real credential ever enters Git—even in an older commit—rotate or revoke
it immediately. Removing it in a later commit is not sufficient.

## Limitations

- The Twilio Sandbox is intended for development, not production.
- One supported audio attachment is processed per incoming message.
- Replies are capped and there are no automatic retries for ambiguous paid
  operations.
- A hosted production instance requires PostgreSQL and operational monitoring.
- Duration inspection is a guardrail, not full malicious-media isolation.
- Twilio and the configured transcription provider process the audio; this is
  not an end-to-end local solution.
- The hosted `whisper-1` API used by this snapshot is scheduled to shut down on
  26 February 2027. This archived code may therefore require a model migration
  to run after that date.

## Further documentation

- [Architecture](docs/architecture.rst)
- [Security model](docs/security.rst)
- [Testing](docs/testing.rst)
- [Decision records](docs/decisions.rst)
- [Historical deployment plan](docs/deployment.rst)
- [Historical delivery plan](docs/delivery.rst)

The deployment and delivery documents are retained as engineering notes. Their
remaining production gates are intentionally not being pursued.

## License

[GNU General Public License v3.0](LICENSE)
