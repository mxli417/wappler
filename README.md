![Wappler](https://raw.githubusercontent.com/mxli417/wappler/HEAD/assets/dalle-wappler.png)

# Wappler

Wappler was an experiment in transcribing WhatsApp voice notes with Twilio and
OpenAI. A signed Twilio webhook accepts the message, stores a job, transcribes
the audio, and sends the text back to WhatsApp.

The experiment is finished. The complete flow worked with a real phone through
the Twilio Sandbox and ngrok on 17 October 2026. I am keeping the repository as
a reference, but I do not plan to register a production WhatsApp Business
Account or run this as a hosted service.

The code includes the webhook, a small database-backed queue, background
workers, duplicate protection, quotas, media limits, and tests around the
Twilio and OpenAI boundaries. SQLite is enough for the local demo; the unused
Render plan expected PostgreSQL.

## Run it locally

You need Python 3.11, [uv](https://docs.astral.sh/uv/), an OpenAI API key, a
Twilio account with the WhatsApp Sandbox enabled, and ngrok.

```powershell
git clone https://github.com/mxli417/wappler.git
cd wappler
uv sync --frozen --extra dev
Copy-Item .env-template .env
```

Fill in `.env`:

```dotenv
OPENAI_API_KEY="<OpenAI API key>"
TWILIO_SID="<Twilio Account SID>"
TWILIO_TOKEN="<Twilio Auth Token>"

TWILIO_WHATSAPP_FROM="whatsapp:+<Twilio Sandbox number>"
ALLOWED_WHATSAPP_SENDERS="whatsapp:+<your phone number>"
TWILIO_TEST_MSG_TO="whatsapp:+<your phone number>"

TWILIO_APP_URL="https://<your ngrok domain>/v0/twilio"
ENVIRONMENT="dev"
DATABASE_URL="sqlite:///wappler.db"
```

`TWILIO_WHATSAPP_FROM` is the Sandbox number. The allowed sender and test
recipient are your own phone—the one that joined the Sandbox. The older
`TWILIO_TEST_MSG_FROM` name is only kept as a compatibility fallback.

Never commit `.env`.

## Connect the Sandbox

1. Open Twilio's WhatsApp Sandbox and send its `join <sandbox-code>` message
   from your phone.
2. Start ngrok:

   ```powershell
   ngrok http 8000
   ```

3. Put the resulting HTTPS URL plus `/v0/twilio` in both `TWILIO_APP_URL` and
   Twilio's **When a message comes in** field. Select `POST`.
4. Start Wappler in another terminal:

   ```powershell
   uv run --frozen uvicorn wappler.api:wappler_app --reload --port 8000
   ```

5. Check `http://localhost:8000/heartbeat` and
   `http://localhost:8000/ready`, then send a short voice note to the Sandbox.

The public webhook URL must match exactly in Twilio and `.env`; otherwise the
signature check returns `403`. When ngrok gives you a new hostname, update both
places and restart Wappler. Requests can be inspected at
`http://127.0.0.1:4040`.

## Tests

The normal suite uses dummy settings and blocks external HTTP calls:

```powershell
uv run --frozen --extra dev pytest
```

The final local run completed with 94 passing tests and 14 expected skips.
Formatting, packaging, dependency auditing, PostgreSQL checks, and Sphinx builds
also run in GitHub Actions.

The following tests are deliberately opt-in because they contact paid services:

```powershell
# Two OpenAI transcription requests; no WhatsApp message
uv run --frozen --extra dev pytest --live -m openai_live tests/integration/test_live.py -v -rP

# One real outbound WhatsApp message
uv run --frozen --extra dev pytest --live -m twilio_live tests/integration/test_live.py -v
```

## Where the project stops

This is a Sandbox demonstration, not a production messaging service. It handles
one supported audio attachment at a time, has no delivery callbacks or automatic
retry scheme, and still sends audio through Twilio and OpenAI.

A static frontend cannot safely hold the provider credentials needed by this
version. A separate local-first phone app, with an on-device speech model, is a
better direction if the goal is private transcription without WABA, webhooks,
or hosted infrastructure.

The hosted `whisper-1` API used here is scheduled to shut down on 26 February
2027, so this snapshot may need a model change if it is revived later.

## Security

`.env`, local databases, tunnel configuration, certificates, and private audio
are ignored. GitHub Actions use read-only repository permissions and pinned
action revisions. If a real credential ever reaches Git history, revoke it;
deleting it in a later commit is not enough. See [SECURITY.md](SECURITY.md) for
reporting guidance.

After a demo, stop ngrok, remove the Twilio webhook, and revoke provider keys
that were created only for this project.

## Documentation

- [Getting started](docs/getting-started.rst)
- [Architecture](docs/architecture.rst)
- [Testing](docs/testing.rst)
- [Security](docs/security.rst)
- [Decision records](docs/decisions.rst)

The longer deployment and delivery documents remain in `docs/` as historical
engineering notes. Sphinx builds the full documentation into
`docs/_build/html`; CI also uploads it as an artifact.

## License

[GNU General Public License v3.0](LICENSE)
