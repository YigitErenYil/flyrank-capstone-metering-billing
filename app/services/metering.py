import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import UsageEvent
from app.services import quota as quota_service
from app.services.cost import (
    calculate_api_call_cost_cents,
    calculate_ai_token_cost_cents,
    total_ai_tokens,
)


def record_generate_usage(
    db: Session,
    tenant_id: uuid.UUID,
    idempotency_key: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
):
    """
    The heart of the capstone: exactly-once metering.

    Flow:
    1. Check if this idempotency_key was already used -> if so, return the
       EXISTING event (no new row, no quota re-check). This is what makes a
       retried request safe.
    2. Otherwise, check quota BEFORE writing.
    3. Insert. The DB unique constraint on idempotency_key is the real
       guarantee against races (two concurrent requests with the same key) —
       the pre-check above is just the fast path.

    Returns (usage_event, replayed: bool).
    """
    existing = db.query(UsageEvent).filter(
        UsageEvent.idempotency_key == idempotency_key
    ).first()
    if existing is not None:
        return existing, True

    ai_tokens_qty = total_ai_tokens(input_tokens, cached_input_tokens, output_tokens, reasoning_tokens)

    # This raises QuotaExceeded / PaymentRequired if not allowed — caller (router) handles it.
    quota_service.check_quota(
        db, tenant_id,
        additional_api_calls=1,
        additional_ai_tokens=ai_tokens_qty,
    )

    api_cost = calculate_api_call_cost_cents()
    token_cost = calculate_ai_token_cost_cents(
        input_tokens, cached_input_tokens, output_tokens, reasoning_tokens
    )

    event = UsageEvent(
        tenant_id=tenant_id,
        type="api_call",  # this dummy endpoint bills as one api_call PLUS its token usage
        quantity=1,
        idempotency_key=idempotency_key,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_cents=api_cost + token_cost,
    )

    # We also need an ai_tokens usage row so GET /usage's token rollup works
    # (quota check above already validated both dimensions together).
    token_event = UsageEvent(
        tenant_id=tenant_id,
        type="ai_tokens",
        quantity=ai_tokens_qty,
        idempotency_key=f"{idempotency_key}:tokens",  # derived, still unique per request
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_cents=0,  # cost already attributed to the api_call row, avoid double counting cost
    )

    db.add(event)
    db.add(token_event)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race: another request with the same key committed first.
        db.rollback()
        existing = db.query(UsageEvent).filter(
            UsageEvent.idempotency_key == idempotency_key
        ).first()
        return existing, True

    db.refresh(event)
    return event, False
