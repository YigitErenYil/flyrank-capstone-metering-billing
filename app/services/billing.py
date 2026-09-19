import os
import uuid
import stripe
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import (
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_ID_PRO,
    FRONTEND_SUCCESS_URL,
    FRONTEND_CANCEL_URL,
)
from app.models import Subscription, ProcessedStripeEvent

stripe.api_key = STRIPE_SECRET_KEY

# Using stripe-mock (Stripe's own open-source fake API server, run as the
# `stripe-mock` service in docker-compose) instead of the real Stripe API.
# This lets the whole checkout + webhook flow be built and evaluated with
# real Stripe SDK calls and real request/response shapes, without needing a
# live Stripe account. FlyRank staff have confirmed this "SDK with mocked/
# test fixtures" approach is an accepted alternative when Stripe doesn't
# support the intern's country (Stripe does not currently support Turkey).
if os.getenv("USE_STRIPE_MOCK", "true").lower() == "true":
    stripe.api_base = "http://stripe-mock:12111"


def create_checkout_session(db: Session, tenant_id: uuid.UUID) -> str:
    """Creates a Stripe Checkout session (test mode) for Free -> Pro upgrade.
    Returns the session URL the client should redirect the browser to."""
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub is None:
        raise ValueError(f"No subscription found for tenant {tenant_id}")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_ID_PRO, "quantity": 1}],
        success_url=FRONTEND_SUCCESS_URL + "?session_id={CHECKOUT_SESSION_ID}",
        cancel_url=FRONTEND_CANCEL_URL,
        client_reference_id=str(tenant_id),
        customer=sub.stripe_customer_id,  # None on first checkout — Stripe creates one
    )
    return session.url


def _already_processed(db: Session, stripe_event_id: str) -> bool:
    return db.query(ProcessedStripeEvent).filter(
        ProcessedStripeEvent.stripe_event_id == stripe_event_id
    ).first() is not None


def _mark_processed(db: Session, stripe_event_id: str):
    db.add(ProcessedStripeEvent(stripe_event_id=stripe_event_id))
    try:
        db.commit()
    except IntegrityError:
        # Raced with another delivery of the same event — already recorded, fine.
        db.rollback()


def handle_checkout_completed(db: Session, event_data: dict):
    session = event_data["object"]
    tenant_id = session.get("client_reference_id")
    if not tenant_id:
        return  # not one of ours

    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    if sub is None:
        return

    sub.plan_id = "pro"
    sub.status = "active"
    sub.stripe_customer_id = session.get("customer")
    sub.stripe_subscription_id = session.get("subscription")
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()


def handle_subscription_updated(db: Session, event_data: dict):
    subscription = event_data["object"]
    stripe_sub_id = subscription["id"]

    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).first()
    if sub is None:
        return

    stripe_status = subscription["status"]  # active, past_due, canceled, etc.
    sub.status = "active" if stripe_status == "active" else (
        "past_due" if stripe_status in ("past_due", "unpaid", "incomplete") else "canceled"
    )
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()


def handle_subscription_deleted(db: Session, event_data: dict):
    subscription = event_data["object"]
    stripe_sub_id = subscription["id"]

    sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).first()
    if sub is None:
        return

    sub.plan_id = "free"
    sub.status = "canceled"
    sub.updated_at = datetime.now(timezone.utc)
    db.commit()


HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}


def process_stripe_event(db: Session, event: dict) -> str:
    """Dedupes by event id, then dispatches to the right handler.
    Returns a short status string for logging/response purposes."""
    event_id = event["id"]
    event_type = event["type"]

    if _already_processed(db, event_id):
        return "duplicate_ignored"

    handler = HANDLERS.get(event_type)
    if handler:
        handler(db, event["data"])

    _mark_processed(db, event_id)
    return "processed" if handler else "ignored_unhandled_type"
