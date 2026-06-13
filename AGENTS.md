# AGENTS.md — Chasqui WhatsApp Gateway

The **WhatsApp channel adapter** for Chasqui: a thin, **stateless** bridge between WhatsApp and the core. Part of the [`chasqui-stack`](https://github.com/chasqui-stack/chasqui) stack — read the parent's [`docs/ARCHITECTURE.md`](https://github.com/chasqui-stack/chasqui/blob/main/docs/ARCHITECTURE.md) first.

## Job

1. Receive WhatsApp webhooks (text, audio, image, buttons).
2. **Normalize to the canonical message** (`docs/ARCHITECTURE.md` §5). Media (image/audio) is downloaded and inlined as a base64 `data:` URI in `media_url` (`app/services/media.py`) — Meta media URLs expire in minutes and the channel-agnostic core can never fetch them.
3. `POST` the core's `/ingest`.
4. Render the core's canonical response back to WhatsApp. An **empty `messages` list is silence** (human-mode conversations) — render nothing.
5. Expose **`POST /send`** (ADR-004, `app/services/sender.py`): the canonical **outbound** contract, mirror of `/ingest`, same `INTERNAL_API_KEY`. Types: `text`, and `image`/`document`/`audio` with `media_url` as a base64 `data:` URI (mirror of inbound — never a URL) mapped to PyWa `send_image`/`send_document`/`send_audio` (bytes + mime_type). Addressed by `wa_id` (no BSUID send endpoint at Meta yet → `NO_WA_ID` error); PyWa's `ReEngagementMessage` (24h window, code 131047) maps to `WINDOW_EXPIRED` so the admin panel can explain it. **`WA_PHONE_ID` is required for `/send`** — client-initiated sends can't infer the sender like replies do.

**Ack Meta fast** (return 200 immediately) and process against the core asynchronously.

## Stack

Python · **PyWa 4.x (BSUID-first)** · FastAPI · httpx · Sentry · `uv`.

## BSUID (see ARCHITECTURE §10)

- `user.bsuid` is the **primary** identifier → maps to canonical `contact.external_id` (in the handlers). `user.wa_id` is optional/secondary.
- Do **not** override PyWa's `user_identifier_priority` (wa_id-first): it only controls how **replies are addressed**, and Meta's API does not yet support BSUID-based send endpoints. PyWa will flip its default when it does.
- Install: `uv add "pywa[fastapi]"` (4.x is now a stable release).

## Dev

```bash
cp .env.example .env     # WhatsApp Business creds + CORE_URL
uv sync
make dev
```

## Planning

PRPs and the sprint plan live in the **parent repo** (`../PRPs`, `../docs`).

## Don't

- Add a database or business logic — this service is **stateless**.
- Use `wa_id` as the primary identifier (use `bsuid`).
- Block the webhook waiting on the core (ack first, process async).
- **Hardcode user-facing literals.** The agent localizes per-user via the system prompt; the few non-agent replies (core unreachable, unsupported type) are English defaults configurable via `.env` (`ERROR_REPLY`/`UNSUPPORTED_REPLY`) — set them per-deployment in your users' language. They must be gateway-local: they fire exactly when the core is unreachable.
- **Send canonical text raw.** `message.text` is Markdown (ARCHITECTURE §5, [ADR-007](https://github.com/chasqui-stack/chasqui/blob/main/docs/design/adr-007-canonical-markdown-rendering.md)); the gateway renders it to WhatsApp syntax (`app/services/formatting.py`) before replying. Don't push channel formatting into the core.
