"""Authenticated, bounded webhook admission; vendor work runs from stored jobs."""

import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool
from twilio.request_validator import RequestValidator

from wappler.jobs import JobStore
from wappler.speech2text.whispr import MEDIA_SUFFIXES, validate_media_url
from wappler.utils.config import Settings
from wappler.worker import Workers, event

MAX_WEBHOOK_BYTES = 64 * 1024


async def bounded_form(req):
    """Bound the actual stream, even without Content-Length, before parsing."""
    try:
        async with asyncio.timeout(10):
            body = bytearray()
            async for chunk in req.stream():
                if len(body) + len(chunk) > MAX_WEBHOOK_BYTES:
                    raise HTTPException(status_code=413, detail="Webhook too large")
                body.extend(chunk)
    except TimeoutError:
        raise HTTPException(status_code=408, detail="Webhook body timed out") from None

    async def receive():
        return {"type": "http.request", "body": bytes(body), "more_body": False}

    parsed = Request(req.scope, receive)
    try:
        form = await parsed.form(max_files=0, max_fields=100, max_part_size=MAX_WEBHOOK_BYTES)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid form data") from None
    if len(form.multi_items()) > 100 or len(form.multi_items()) != len(form):
        raise HTTPException(status_code=400, detail="Too many or repeated form fields")
    return form


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an isolated app; imports do not read secrets or contact vendors."""

    @asynccontextmanager
    async def lifespan(app):
        current = settings or Settings.from_env()
        current.validate()
        store = JobStore(current)
        try:
            await run_in_threadpool(store.initialize)
        except Exception:
            raise RuntimeError("Job database initialization failed; check DATABASE_URL") from None
        workers = Workers(store)
        app.state.settings = current
        app.state.store = store
        app.state.workers = workers
        if current.worker_enabled:
            workers.start()
        try:
            yield
        finally:
            await run_in_threadpool(workers.stop)

    app = FastAPI(title="Wappler", version="0.0.1", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    @app.get("/heartbeat")
    def heartbeat():
        """Liveness only; no paid upstream probes."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(req: Request):
        """Check storage availability without exposing operational counts."""
        try:
            await run_in_threadpool(req.app.state.store.snapshot)
        except Exception:
            raise HTTPException(status_code=503, detail="Storage unavailable") from None
        return {"status": "ready"}

    @app.post("/v0/twilio")
    async def speech2text(req: Request):
        """Authenticate, reserve quota and persist a job before acknowledging."""
        current = req.app.state.settings
        content_type = req.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/x-www-form-urlencoded", "multipart/form-data"}:
            raise HTTPException(status_code=415, detail="Expected form data")
        signature = req.headers.get("X-Twilio-Signature", "")
        if not signature or len(signature) > 128:
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        form = await bounded_form(req)
        public_url = current.webhook_url or str(req.url)
        if req.url.query != urlsplit(public_url).query or not RequestValidator(current.twilio_token).validate(
            public_url, form, signature
        ):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")
        sender = form.get("From")
        if not isinstance(sender, str) or not sender:
            raise HTTPException(status_code=400, detail="Missing sender")
        if sender not in current.allowed_senders:
            raise HTTPException(status_code=403, detail="Sender is not allowed")
        if form.get("AccountSid") != current.twilio_sid or form.get("To") != current.whatsapp_from:
            raise HTTPException(status_code=403, detail="Account or recipient mismatch")
        message = form.get("MessageSid")
        if not isinstance(message, str) or not message or len(message) > 64:
            raise HTTPException(status_code=400, detail="Invalid MessageSid")
        try:
            count = int(form.get("NumMedia", "0"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid NumMedia") from None
        if count < 0:
            raise HTTPException(status_code=400, detail="Invalid NumMedia")
        media_url = form.get("MediaUrl0")
        mime = str(form.get("MediaContentType0", "")).split(";", 1)[0].strip().lower()
        if count == 1 and (not isinstance(media_url, str) or not media_url):
            raise HTTPException(status_code=400, detail="Missing media URL")
        supported = count == 1 and mime in MEDIA_SUFFIXES
        if supported:
            try:
                validate_media_url(media_url)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid media URL") from None
        try:
            outcome, job_id = await run_in_threadpool(
                req.app.state.store.admit,
                current.twilio_sid,
                message,
                sender,
                media_url if supported else None,
                mime if supported else "",
            )
        except Exception as exc:
            event("admission_store_unavailable", error=type(exc).__name__)
            raise HTTPException(status_code=503, detail="Storage unavailable") from None
        event("admission", outcome=outcome, job_id=job_id)
        if outcome == "limited":
            raise HTTPException(status_code=429, detail="Operation quota exceeded", headers={"Retry-After": "3600"})
        if outcome in {"full", "disabled"}:
            raise HTTPException(status_code=503, detail="Processing unavailable", headers={"Retry-After": "60"})
        if outcome == "accepted":
            req.app.state.workers.notify()
        return Response(content="<Response/>", media_type="application/xml")

    return app


wappler_app = create_app()
