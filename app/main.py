import asyncio
import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from pywa_async import WhatsApp, filters, types

from app.core.config import settings

# Initialize Sentry only when a DSN is configured (i.e. production)
if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.1)

from app.handlers.message_handlers import (  # noqa: E402
    handle_audio_message,
    handle_callback_button,
    handle_image_message,
    handle_text_message,
    handle_unsupported_message,
)
from app.services.core_client import CoreClient  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

core_client: CoreClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global core_client
    core_client = CoreClient(base_url=settings.core_url, api_key=settings.internal_api_key)
    logger.info("Chasqui WhatsApp gateway started — core=%s", settings.core_url)
    yield
    if core_client:
        await core_client.close()


app = FastAPI(
    title="Chasqui WhatsApp Gateway",
    description="Stateless WhatsApp channel adapter",
    version="0.1.0",
    lifespan=lifespan,
)

wa_kwargs = dict(
    token=settings.wa_token,
    server=app,
    verify_token=settings.wa_verify_token,
    app_id=settings.wa_app_id,
    app_secret=settings.wa_app_secret,
    webhook_endpoint="/webhook",
    skip_duplicate_updates=True,
    # NOTE on BSUID (ARCHITECTURE §10): identity is BSUID-first — the handlers
    # map `user.bsuid` → canonical `contact.external_id`. We deliberately keep
    # PyWa's default `user_identifier_priority` (wa_id first) because it only
    # controls how REPLIES are addressed, and Meta's API does not yet support
    # BSUID-based send endpoints (PyWa will flip its default when it does).
)
# Register callback_url only in development (e.g. ngrok). In production the
# webhook is configured manually in Meta Business Suite.
if settings.wa_callback_url:
    wa_kwargs["callback_url"] = settings.wa_callback_url

wa = WhatsApp(**wa_kwargs)


def get_core() -> CoreClient:
    if core_client is None:
        raise RuntimeError("CoreClient not initialized")
    return core_client


# ---------------------------------------------------------------------------
# Ack fast (sprint 2): PyWa awaits handlers BEFORE answering Meta's webhook,
# so handlers must not block — we dispatch the core round-trip as a background
# task and return immediately. Meta gets its 200 in milliseconds.
# ---------------------------------------------------------------------------
_background_tasks: set[asyncio.Task] = set()


def _dispatch(coro) -> None:
    """Fire-and-forget a handler coroutine (kept referenced until done)."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@wa.on_message(filters.text)
async def on_text_message(client: WhatsApp, msg: types.Message):
    _dispatch(handle_text_message(client, msg, get_core()))


@wa.on_message(filters.audio)
async def on_audio_message(client: WhatsApp, msg: types.Message):
    _dispatch(handle_audio_message(client, msg, get_core()))


@wa.on_message(filters.image)
async def on_image_message(client: WhatsApp, msg: types.Message):
    _dispatch(handle_image_message(client, msg, get_core()))


@wa.on_callback_button
async def on_callback_button(client: WhatsApp, cb: types.CallbackButton):
    _dispatch(handle_callback_button(client, cb, get_core()))


@wa.on_message()
async def on_other_message(client: WhatsApp, msg: types.Message):
    _dispatch(handle_unsupported_message(client, msg))


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "chasqui-whatsapp"}
