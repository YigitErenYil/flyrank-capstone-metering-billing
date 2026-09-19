"""
Send a self-signed, Stripe-shaped webhook event to the local API.

Why this exists: Stripe does not currently support creating accounts in
Turkey, so a live Stripe test-mode account isn't available (confirmed as an
accepted alternative by FlyRank staff for exactly this situation — see
BUILDLOG.md: "use the SDK with mocked/test fixtures").

This script builds an event payload shaped exactly like a real Stripe event,
signs it the same way Stripe does (HMAC-SHA256 over "{timestamp}.{payload}"
using the shared webhook secret), and POSTs it to /webhooks/stripe. This
exercises the REAL signature-verification, dedup, and handler code in
app/services/billing.py and app/routers/webhooks.py — only the event's
origin is simulated, not the verification logic itself.

Usage (run from the host machine, python already installed):
    python fixtures/send_event.py checkout_completed <tenant_id>
    python fixtures/send_event.py subscription_updated <stripe_subscription_id> [status]
    python fixtures/send_event.py subscription_deleted <stripe_subscription_id>
    python fixtures/send_event.py replay <tenant_id>      # sends the same event id twice
    python fixtures/send_event.py forged <tenant_id>      # signs with a WRONG secret -> expect 400

Reads STRIPE_WEBHOOK_SECRET from the environment if set, otherwise uses the
same placeholder default as .env.example — make sure this matches whatever
is in your .env so the "real" (non-forged) sends verify successfully.
"""
import sys
import os
import json
import time
import hmac
import hashlib
import uuid
import argparse
import urllib.request
import urllib.error

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "http://localhost:8000/webhooks/stripe")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")


def sign(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={signature}"


def send(event: dict, secret: str = None):
    secret = secret or WEBHOOK_SECRET
    payload = json.dumps(event).encode()
    header = sign(payload, secret)

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Stripe-Signature": header},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as e:
        print(e.code, e.read().decode())


def checkout_completed_event(tenant_id, customer_id="cus_test_123", subscription_id="sub_test_123", event_id=None):
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": f"cs_test_{uuid.uuid4().hex[:16]}",
            "client_reference_id": tenant_id,
            "customer": customer_id,
            "subscription": subscription_id,
        }},
    }


def subscription_updated_event(stripe_subscription_id, status="active", event_id=None):
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": stripe_subscription_id, "status": status}},
    }


def subscription_deleted_event(stripe_subscription_id, event_id=None):
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:24]}",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": stripe_subscription_id}},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("checkout_completed")
    p1.add_argument("tenant_id")
    p1.add_argument("--customer-id", default="cus_test_123")
    p1.add_argument("--subscription-id", default="sub_test_123")

    p2 = sub.add_parser("subscription_updated")
    p2.add_argument("stripe_subscription_id")
    p2.add_argument("status", nargs="?", default="active")

    p3 = sub.add_parser("subscription_deleted")
    p3.add_argument("stripe_subscription_id")

    p4 = sub.add_parser("replay")
    p4.add_argument("tenant_id")
    p4.add_argument("--customer-id", default="cus_test_123")
    p4.add_argument("--subscription-id", default="sub_test_123")

    p5 = sub.add_parser("forged")
    p5.add_argument("tenant_id")

    args = parser.parse_args()

    if args.command == "checkout_completed":
        send(checkout_completed_event(args.tenant_id, args.customer_id, args.subscription_id))

    elif args.command == "subscription_updated":
        send(subscription_updated_event(args.stripe_subscription_id, args.status))

    elif args.command == "subscription_deleted":
        send(subscription_deleted_event(args.stripe_subscription_id))

    elif args.command == "replay":
        fixed_id = "evt_fixed_replay_test"
        event = checkout_completed_event(args.tenant_id, args.customer_id, args.subscription_id, event_id=fixed_id)
        print("First send (should process):")
        send(event)
        print("Replay send, same event id (should say duplicate_ignored):")
        send(event)

    elif args.command == "forged":
        event = checkout_completed_event(args.tenant_id)
        print("Sending with a WRONG secret on purpose (should be 400):")
        send(event, secret="whsec_wrong_secret_on_purpose")
