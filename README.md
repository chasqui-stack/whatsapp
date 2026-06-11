# Chasqui WhatsApp Gateway

PyWa-based WhatsApp channel adapter for [Chasqui](https://github.com/chasqui-stack/chasqui), the open-source stack for building WhatsApp AI agents.

A thin, **stateless** bridge: it receives WhatsApp webhooks, normalizes them to Chasqui's canonical message contract, forwards them to the [core](https://github.com/chasqui-stack/core)'s `/ingest`, and renders replies back to WhatsApp. No database, no business logic.

It also implements the **canonical outbound contract** (`POST /send`, ADR-004) — the mirror of `/ingest`, authenticated with the same `INTERNAL_API_KEY` — so operators can reply from the admin panel (human-handoff inbox). Sends are addressed by `wa_id` (Meta has no BSUID send endpoint yet); a send outside WhatsApp's 24h customer-service window maps to a clear `WINDOW_EXPIRED` error.

## Stack

Python · PyWa 4.x (beta, BSUID-first) · FastAPI · httpx · Sentry · `uv`.

## Local dev

```bash
cp .env.example .env     # WhatsApp Business credentials + CORE_URL
uv sync
make dev
```

> Uses **PyWa 4.x** (`uv add "pywa --prerelease=allow"`) for WhatsApp's BSUID identity migration — see the parent's [`docs/ARCHITECTURE.md`](https://github.com/chasqui-stack/chasqui/blob/main/docs/ARCHITECTURE.md) §10.

## License

[Apache-2.0](./LICENSE).
