import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UsageEvent, Subscription, Plan


class QuotaExceeded(Exception):
    def __init__(self, used: int, limit: int, usage_type: str):
        self.used = used
        self.limit = limit
        self.usage_type = usage_type
        super().__init__(f"{usage_type} quota exceeded: {used}/{limit}")


class PaymentRequired(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def get_current_usage(db: Session, tenant_id: uuid.UUID) -> dict:
    """Rolls up all usage_events for a tenant (billing period simplification:
    all-time totals reset would require period tracking — MVP treats the
    subscription's current_period as the window; see EVIDENCE.md for scope note)."""
    api_calls_used = db.query(func.count(UsageEvent.id)).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.type == "api_call",
    ).scalar() or 0

    ai_tokens_used = db.query(func.coalesce(func.sum(UsageEvent.quantity), 0)).filter(
        UsageEvent.tenant_id == tenant_id,
        UsageEvent.type == "ai_tokens",
    ).scalar() or 0

    return {"api_calls": api_calls_used, "ai_tokens": ai_tokens_used}


def get_tenant_plan(db: Session, tenant_id: uuid.UUID) -> tuple[Subscription, Plan]:
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub is None:
        raise ValueError(f"No subscription found for tenant {tenant_id}")
    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first()
    return sub, plan


def check_quota(db: Session, tenant_id: uuid.UUID, additional_api_calls: int, additional_ai_tokens: int):
    """Raises PaymentRequired if subscription inactive, QuotaExceeded if over plan limit.
    Returns (subscription, plan, current_usage) if allowed."""
    sub, plan = get_tenant_plan(db, tenant_id)

    if sub.status != "active":
        raise PaymentRequired("Subscription inactive — upgrade to continue")

    usage = get_current_usage(db, tenant_id)

    if additional_api_calls and (usage["api_calls"] + additional_api_calls) > plan.monthly_api_calls:
        raise QuotaExceeded(usage["api_calls"], plan.monthly_api_calls, "api_calls")

    if additional_ai_tokens and (usage["ai_tokens"] + additional_ai_tokens) > plan.monthly_ai_tokens:
        raise QuotaExceeded(usage["ai_tokens"], plan.monthly_ai_tokens, "ai_tokens")

    return sub, plan, usage
