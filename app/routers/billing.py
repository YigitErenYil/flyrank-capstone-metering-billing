import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import billing as billing_service

router = APIRouter()


@router.post("/billing/checkout")
def create_checkout(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        url = billing_service.create_checkout_session(db, tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"checkout_url": url}


@router.get("/billing/success")
def checkout_success():
    return {"message": "Checkout complete. Plan will update once the webhook is processed."}


@router.get("/billing/cancel")
def checkout_cancel():
    return {"message": "Checkout canceled."}
