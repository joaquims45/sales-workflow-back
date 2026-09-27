# Sales Workflow — Backend (`sales-workflow-back`)

Django/DRF backend for **Sales Workflow**: an agentic sales workflow engine
that understands when to continue, interrupt, branch, resume or replace an
ongoing sales process. See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for
the full design (SalesState, routing, Jev, RAG, checkout, events).

This backend runs fully offline out of the box: SQLite instead of Postgres,
an in-memory channel layer instead of Redis, a deterministic hashing
embedding instead of a real embeddings API, and `MockPaymentProvider`
instead of Mercado Pago. Nothing here requires an external account except
Jev routing, which is optional (see below).

## Requirements

- **Python 3.14+** (required by the `jev`/`typesafe-sdk` routing integration)
- No database or message broker required to get started — Postgres/Redis
  are optional upgrades, wired the same way in every environment via `.env`

## Quickstart

```bash
# from sales-workflow-back/
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env             # defaults already work as-is

python manage.py migrate
python manage.py loaddata demo_catalog   # fictional products (§37)
python manage.py reindex_products        # builds the FAISS index
python manage.py createsuperuser         # optional, for /admin/

python manage.py runserver
```

The server listens on `http://127.0.0.1:8000/`. `daphne` (already in
`INSTALLED_APPS`) serves both HTTP and the WebSocket endpoint through
`runserver`, so no separate ASGI command is needed in development.

## Try the conversation end-to-end

```bash
# 1. Create a conversation
curl -X POST http://127.0.0.1:8000/api/conversations/
# => {"id": 1, "customer": null, "is_active": true, "created_at": "...", "messages": []}

# 2. Talk to it (repeat with the conversation id from step 1)
curl -X POST http://127.0.0.1:8000/api/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -d '{"content": "Busco una notebook para programar y jugar."}'

curl -X POST http://127.0.0.1:8000/api/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -d '{"content": "Tengo hasta $1.500.000."}'

curl -X POST http://127.0.0.1:8000/api/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -d '{"content": "¿Hacen envíos a Santa Fe?"}'

curl -X POST http://127.0.0.1:8000/api/conversations/1/messages/ \
  -H "Content-Type: application/json" \
  -d '{"content": "Perfecto, quiero comprarla."}'

# 3. Inspect the structured state and the trace at any point
curl http://127.0.0.1:8000/api/conversations/1/state/
curl http://127.0.0.1:8000/api/conversations/1/trace/

# 4. Simulate the payment (MockPaymentProvider) — checkout_url from step 2's
#    last response is /mock-checkout/<external_reference>/
curl -X POST http://127.0.0.1:8000/mock-checkout/<external_reference>/approve/
```

You should see the shipping question answered without losing the notebook
search (`SIDE_QUERY` → `RESUME`), and the final message create an `Order`
and a `Payment` in `PENDING`, visible in `/admin/` or via the mock-checkout
endpoint above.

## Running tests

```bash
python manage.py test
```

The full suite runs against SQLite with no external services — it never
calls Jev, an LLM, FAISS-with-a-real-model, or a real payment gateway.

## Configuration

All configuration is via environment variables (`.env`, see
`.env.example`). Nothing has a real secret checked in.

| Variable | Default | Notes |
|---|---|---|
| `DEBUG` | `True` | |
| `SECRET_KEY` | dev key | set a real one outside local dev |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | |
| `DATABASE_URL` | SQLite file | point at Postgres for anything beyond a smoke test |
| `FAISS_INDEX_PATH` | `./data/faiss_index.bin` | rebuild with `manage.py reindex_products` |
| `TYPESAFE_API_KEY` | unset | optional — without it, routing falls back to a keyword heuristic instead of Jev (§11/§12) |
| `JEV_CONFIDENCE_HIGH` / `JEV_CONFIDENCE_LOW` | `0.85` / `0.6` | routing confidence thresholds |
| `REDIS_URL` | unset | optional — without it, WebSocket events use an in-memory channel layer (single process) |
| `PAYMENT_PROVIDER` | `mock` | set to `mercadopago` once that provider exists and is configured |

## Project layout

See [`../ARCHITECTURE.md`](../ARCHITECTURE.md) §22 for the reasoning; in short:

- `apps/` — Django domain apps (catalog, customers, conversations, orders, payments, analytics, accounts)
- `workflows/` — LangGraph orchestration: `graph/` (PRODUCT_PURCHASE, SHIPPING_QUERY, SalesState), `routing/` (Jev, confidence thresholds, escalation)
- `tools/` — the only way workflow nodes touch commercial data (search, shipping quotes)
- `rag/` — FAISS indexing/retrieval over the product catalog
- `providers/` — pluggable external-service seams (embeddings, LLM, payments)
- `events/` — the WorkflowEvent bus and its WebSocket transport
