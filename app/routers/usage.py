import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import UsageResponse
from app.services import quota as quota_service
from app.models import UsageEvent
from sqlalchemy import func

router = APIRouter()


@router.get("/usage", response_model=UsageResponse)
def get_usage(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        sub, plan, usage = quota_service.check_quota(
            db, tenant_id, additional_api_calls=0, additional_ai_tokens=0
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    total_cost = db.query(func.coalesce(func.sum(UsageEvent.cost_cents), 0)).filter(
        UsageEvent.tenant_id == tenant_id
    ).scalar() or 0

    return UsageResponse(
        tenant_id=tenant_id,
        plan=plan.id,
        api_calls_used=usage["api_calls"],
        api_calls_limit=plan.monthly_api_calls,
        ai_tokens_used=usage["ai_tokens"],
        ai_tokens_limit=plan.monthly_ai_tokens,
        cost_cents=total_cost,
    )
