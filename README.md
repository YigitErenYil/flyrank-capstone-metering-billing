# Usage Metering & Billing Engine

A backend service answering the three questions every SaaS needs: how much
has this tenant used, what does it cost, and have they hit their plan limit?
Built for the FlyRank Internship Backend Track capstone.

## What it does

- Meters billable usage (API calls + simulated AI tokens) per tenant, with
  **exactly-once semantics** under request retries (idempotency keys).
- Enforces plan quotas before allowing an action, with honest `429`/`402`
  responses.
- Prices AI token usage with real-world rules: cached input tokens cheaper,
  reasoning tokens billed as output, categories priced separately.
- Integrates Stripe subscriptions (Checkout + signature-verified,
  deduplicated webhooks) to move a tenant Free → Pro.

## Architecture

```
Client → POST /generate (Idempotency-Key header)
  → MeterService.record(tenant, usage, idempotency_key)
      | key already seen? → return the ORIGINAL result, no new event
      | else → QuotaService.check() → over limit? → 429 / 402
             → insert usage_events row, compute cost
  → 200 { usage_event_id, cost_cents, remaining_quota, replayed }

GET /usage?tenant_id=  → rollup(usage_events) → { used, limit, cost_cents }

POST /billing/checkout?tenant_id=  → Stripe Checkout session (test mode)

Stripe / fixtures → signed event → POST /webhooks/stripe
  | verify signature (bad sig → 400)
  | dedup by stripe_event_id (replay → no-op)
  | update tenants.subscription (plan / status)
```

Layers: `app/models.py` (data) → `app/services/*.py` (business logic:
metering, quota, cost, billing) → `app/routers/*.py` (HTTP boundary,
Pydantic validation).

## Data model

`tenants`, `plans`, `subscriptions`, `usage_events`, `processed_stripe_events`
— see `DESIGN.md` for the full schema. Every usage/subscription query is
scoped by `tenant_id`; there is no endpoint that reads across tenants.

## Setup & run (clean machine)

Requires Docker Desktop.

```bash
git clone <this-repo-url>
cd flyrank-capstone-metering-billing
cp .env.example .env
docker compose up --build
```

Seed plans + a demo tenant (in a second terminal, once the containers are up):

```bash
docker compose exec api python seed.py
```

This prints a `Demo tenant id` — use it in the requests below.

## Try it

```bash
# Meter a billable call (idempotent — same key twice = one event)
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-key-1" \
  -d '{"tenant_id":"<TENANT_ID>","input_tokens":500,"output_tokens":200}'

# Check usage / cost rollup
curl "http://localhost:8000/usage?tenant_id=<TENANT_ID>"

# Start a (mocked) Stripe Checkout
curl -X POST "http://localhost:8000/billing/checkout?tenant_id=<TENANT_ID>"

# Simulate the resulting webhook (see "Stripe & Turkey" below for why)
python fixtures/send_event.py checkout_completed <TENANT_ID>
```

## Stripe & Turkey — an honest limitation

Stripe does not currently support creating accounts in Turkey. FlyRank staff
confirmed (community answer, screenshot in `BUILDLOG.md`) that building the
Stripe integration against **stripe-mock** (Stripe's own open-source fake API
server) plus self-signed webhook fixtures is an accepted alternative to a
live account.

Concretely:
- `stripe.api_base` is pointed at the `stripe-mock` container, so
  `POST /billing/checkout` makes a real Stripe SDK call, against a server
  that responds with Stripe's real API shapes — just not able to render an
  actual hosted checkout page a browser can complete.
- `fixtures/send_event.py` builds Stripe-shaped webhook events and signs
  them with the same HMAC scheme Stripe uses, so the receiving code
  (`app/routers/webhooks.py`, `app/services/billing.py`) is exercised
  exactly as it would be by a real Stripe webhook delivery — signature
  verification, dedup, and plan-sync all run for real.

What this does **not** prove: an actual browser-driven Checkout session
completed with a real (test) card. That specific step is the one piece that
genuinely requires a live Stripe account.

## Other known limitations

- Billing "period" is simplified to all-time totals per tenant rather than a
  true monthly rolling window (no cron/reset job) — acceptable for the
  capstone's realistic scope, called out here rather than hidden.
- No test suite (optional per the brief); verification is via the curl /
  fixture transcripts in `EVIDENCE.md`.
- Schema is created via `Base.metadata.create_all` rather than Alembic
  migrations.
