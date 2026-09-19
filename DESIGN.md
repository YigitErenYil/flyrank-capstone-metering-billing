# Design Doc — Usage Metering & Billing Engine

## Problem
Every SaaS needs to answer three questions per tenant: how much have they used,
what does it cost, and have they hit their plan's limits? This service answers
all three, safely under retries and concurrent requests.

## Non-goal
No real payments, no invoicing/proration/overage billing in the core build.
Stripe test mode only. AI token usage is simulated — no model calls, no LLM key.

## Data model

```
tenants
  id (pk)
  name
  created_at

plans
  id (pk)              -- 'free' | 'pro'
  name
  monthly_api_calls     -- int, quota
  monthly_ai_tokens      -- int, quota

subscriptions
  id (pk)
  tenant_id (fk -> tenants)
  plan_id (fk -> plans)
  status                 -- 'active' | 'past_due' | 'canceled'
  stripe_customer_id
  stripe_subscription_id
  current_period_start
  current_period_end
  updated_at

usage_events
  id (pk)
  tenant_id (fk -> tenants)
  type                    -- 'api_call' | 'ai_tokens'
  quantity                -- int (cents-equivalent precision for cost math)
  idempotency_key (unique, indexed)
  input_tokens            -- nullable, only for 'ai_tokens'
  cached_input_tokens     -- nullable
  output_tokens           -- nullable
  reasoning_tokens        -- nullable
  created_at

processed_stripe_events
  id (pk)
  stripe_event_id (unique, indexed)  -- for webhook dedup
  processed_at
```

Isolation: every query is scoped by `tenant_id`. No cross-tenant reads.

## Plans & quotas

| Plan | API calls / month | AI tokens / month |
|------|-------------------|--------------------|
| Free | 1,000             | 100,000            |
| Pro  | 10,000            | 1,000,000          |

Test-mode only — "upgrading" to Pro is a simulated Stripe Checkout flow, no
real charge.

## Metering API contract

**`POST /generate`** — the one dummy billable endpoint.

Request:
```
Headers:
  Idempotency-Key: <client-generated UUID, required>
Body:
{
  "tenant_id": "uuid",
  "input_tokens": 500,
  "cached_input_tokens": 100,
  "output_tokens": 200,
  "reasoning_tokens": 50
}
```

Flow:
1. Look up `usage_events` by `idempotency_key`.
   - If found → return the **original** stored response (same status, same body).
     No new row written. No quota re-checked.
2. If not found → compute usage quantity, check tenant's current period usage
   against plan quota.
   - Over limit on **AI tokens** → `429 Too Many Requests`
     `{"error": "quota_exceeded", "message": "AI token quota exceeded for this billing period", "used": ..., "limit": ...}`
   - Tenant subscription `past_due`/`canceled` → `402 Payment Required`
     `{"error": "payment_required", "message": "Subscription inactive — upgrade to continue"}`
   - Otherwise → insert `usage_events` row (with the idempotency key), compute
     cost for this call, return `200` with `{"usage_event_id", "cost_cents", "remaining_quota"}`.

**`GET /usage?tenant_id=`** — rollup.
```
{
  "period_start": "...",
  "period_end": "...",
  "api_calls": {"used": 340, "limit": 1000},
  "ai_tokens": {"used": 52000, "limit": 100000},
  "cost_cents": 1240
}
```

**`POST /billing/checkout`** — creates a Stripe Checkout session for Free → Pro.

**`POST /webhooks/stripe`** — signature-verified, dedup'd via
`processed_stripe_events`, updates `subscriptions`.

## Idempotency strategy

- Client sends `Idempotency-Key` header (a UUID it generates once per logical
  action, reused on retry).
- `usage_events.idempotency_key` has a **unique DB constraint** — this is the
  real guarantee, not just an application-level check (protects against races
  under concurrent retries too).
- On conflict (`IntegrityError` / unique violation), the handler re-reads the
  existing row by that key and returns its stored result instead of erroring.
- Stripe webhook events get the analogous treatment via
  `processed_stripe_events.stripe_event_id` (unique), so a replayed
  `checkout.session.completed` is a no-op the second time.

## Cost calculation rules

- API calls: flat rate per call (pin the constant, e.g. $0.001/call).
- AI tokens, priced separately per category (never summed before pricing):
  - `input_tokens` at full input rate
  - `cached_input_tokens` at a discounted rate
  - `output_tokens` at output rate
  - `reasoning_tokens` at the **output** rate (billed as output, per the brief)
- All money stored/computed as integer cents. No floats anywhere in the cost path.
- Pricing constants live in `config.py`, with a worked example in `EVIDENCE.md`
  proving the totals match by hand.

## Layer separation

- `models.py` — SQLAlchemy models (data layer)
- `services/metering.py`, `services/billing.py`, `services/quota.py` (logic layer)
- `routers/generate.py`, `routers/usage.py`, `routers/webhooks.py` (HTTP layer)
- Validation via Pydantic schemas at the boundary — bad input never reaches
  the service layer as a 500.