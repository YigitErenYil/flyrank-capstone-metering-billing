# Evidence

One proof per requirement box in the capstone brief (Section 6). All
transcripts below are real output from this running system.

## Metering — exactly-once, no double-counting

Same `Idempotency-Key` (`test-key-1`) sent twice:

```
# 1st request
$ curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-key-1" \
  -d '{"tenant_id":"e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a","input_tokens":500,"output_tokens":200}'
{"usage_event_id":"67a54bea-1bea-42df-9f28-396fd5884f49","cost_cents":3,"remaining_api_calls":999,"remaining_ai_tokens":99300,"replayed":false}

# 2nd request, SAME idempotency key
$ curl -X POST http://localhost:8000/generate ... (same body/headers)
{"usage_event_id":"67a54bea-1bea-42df-9f28-396fd5884f49","cost_cents":3,"remaining_api_calls":999,"remaining_ai_tokens":99300,"replayed":true}
```

`usage_event_id` is identical on both responses, `replayed` flips to `true`,
and `remaining_*` did not move — no second usage_events row was written.

## Quotas — correct status codes with explanation

Requesting 150,000 tokens against the Free plan's 100,000/month AI-token
limit:

```
$ curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: test-key-quota" \
  -d '{"tenant_id":"e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a","input_tokens":150000,"output_tokens":0}'
{"detail":{"error":"quota_exceeded","message":"ai_tokens quota exceeded for this billing period","used":700,"limit":100000}}
```

Response carries the `429` status (raised via `HTTPException(status_code=429, ...)`
in `app/routers/generate.py`), the reason (`ai_tokens quota exceeded`), and
the exact used/limit numbers.

## Cost calculation — pinned pricing, proof of correct totals

Pricing constants (`app/config.py`):
- API call: 1 cent
- Input tokens: 3 cents / 1,000
- Cached input tokens: 1 cent / 1,000 (cheaper)
- Output tokens: 6 cents / 1,000
- Reasoning tokens: billed at the output rate (6 cents / 1,000)

Worked example, matching the first `/generate` call above
(500 input tokens, 0 cached, 200 output tokens, 0 reasoning):

```
api_call_cost      = 1
input_cost         = 500 * 3  // 1000 = 1500 // 1000 = 1
cached_input_cost  = 0   * 1  // 1000 = 0
output_cost        = 200 * 6  // 1000 = 1200 // 1000 = 1
reasoning_cost      = 0   * 6  // 1000 = 0
-----------------------------------------------------
total_cost_cents    = 1 + 1 + 0 + 1 + 0 = 3
```

Matches the actual API response: `"cost_cents":3`.

## Stripe integration — checkout + signature-verified, deduplicated webhooks

Checkout session created (via stripe-mock — see README "Stripe & Turkey"):

```
$ curl -X POST "http://localhost:8000/billing/checkout?tenant_id=e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a"
{"checkout_url":"https://checkout.stripe.com/pay/c/cs_test_a1YS1URlnyQCN5fUUduORoQ7Pw41PJqDWkIVQCpJPqkfIhd6tVY8XB1OLY"}
```

Self-signed `checkout.session.completed` webhook flips the tenant Free → Pro:

```
$ python fixtures/send_event.py checkout_completed e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a
200 {"status":"processed"}

$ curl "http://localhost:8000/usage?tenant_id=e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a"
{"tenant_id":"e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a","plan":"pro","api_calls_used":1,"ai_tokens_used":700,"ai_tokens_limit":1000000,"api_calls_limit":10000,"cost_cents":3}
```

Forged signature is rejected (400), nothing changes:

```
$ python fixtures/send_event.py forged e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a
Sending with a WRONG secret on purpose (should be 400):
400 {"detail":"Invalid Stripe signature"}
```

Replayed event (same `stripe_event_id`) is processed once, ignored the
second time:

```
$ python fixtures/send_event.py replay e06de5e8-7cc0-4a5e-8c97-dd18f4c6d89a
First send (should process):
200 {"status":"processed"}
Replay send, same event id (should say duplicate_ignored):
200 {"status":"duplicate_ignored"}
```

## Data model, tests & documentation

- Schema (`app/models.py`): `tenants`, `plans`, `subscriptions`,
  `usage_events`, `processed_stripe_events`.
- Tenant isolation: every query in `app/services/quota.py` and
  `app/services/metering.py` filters by `tenant_id` (e.g.
  `filter(UsageEvent.tenant_id == tenant_id)`); no endpoint accepts a query
  that spans tenants.
- `README.md` includes the architecture diagram, exact setup/run/seed
  commands, and an honest limitations section.
- `capstone.yaml`, `.env.example`, `BUILDLOG.md` present per Section 10.
