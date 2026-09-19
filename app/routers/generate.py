from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import GenerateRequest, GenerateResponse
from app.services import metering as metering_service
from app.services import quota as quota_service
from app.models import Plan

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
def generate(
    payload: GenerateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
):
    if not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required and cannot be empty")

    try:
        event, replayed = metering_service.record_generate_usage(
            db,
            tenant_id=payload.tenant_id,
            idempotency_key=idempotency_key,
            input_tokens=payload.input_tokens,
            cached_input_tokens=payload.cached_input_tokens,
            output_tokens=payload.output_tokens,
            reasoning_tokens=payload.reasoning_tokens,
        )
    except quota_service.QuotaExceeded as e:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "message": f"{e.usage_type} quota exceeded for this billing period",
                "used": e.used,
                "limit": e.limit,
            },
        )
    except quota_service.PaymentRequired as e:
        raise HTTPException(
            status_code=402,
            detail={"error": "payment_required", "message": e.message},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    sub, plan, usage = quota_service.check_quota(
        db, payload.tenant_id, additional_api_calls=0, additional_ai_tokens=0
    )

    return GenerateResponse(
        usage_event_id=event.id,
        cost_cents=event.cost_cents,
        remaining_api_calls=max(plan.monthly_api_calls - usage["api_calls"], 0),
        remaining_ai_tokens=max(plan.monthly_ai_tokens - usage["ai_tokens"], 0),
        replayed=replayed,
    )
