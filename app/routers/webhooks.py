import stripe
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import STRIPE_WEBHOOK_SECRET
from app.services import billing as billing_service

router = APIRouter()


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        # Forged or malformed signature — must reject, never process.
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    status = billing_service.process_stripe_event(db, event)
    return {"status": status}
