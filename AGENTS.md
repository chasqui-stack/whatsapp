# AGENTS.md — Chasqui WhatsApp Gateway

The **WhatsApp channel adapter** for Chasqui: a thin, **stateless** bridge between WhatsApp and the core. Part of the [`chasqui-stack`](https://github.com/chasqui-stack/chasqui) stack — read the parent's [`docs/ARCHITECTURE.md`](https://github.com/chasqui-stack/chasqui/blob/main/docs/ARCHITECTURE.md) first.

## Job

1. Receive WhatsApp webhooks (text, audio, image, buttons).
2. **Normalize to the canonical message** (`docs/ARCHITECTURE.md` §5).
3. `POST` the core's `/ingest`.
4. Render the core's canonical response back to WhatsApp.

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
