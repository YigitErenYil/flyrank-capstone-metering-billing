import uuid
from typing import Optional
from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    tenant_id: uuid.UUID
    input_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)


class GenerateResponse(BaseModel):
    usage_event_id: uuid.UUID
    cost_cents: int
    remaining_api_calls: int
    remaining_ai_tokens: int
    replayed: bool = False  # true if this was an idempotent replay, not a new event


class UsageResponse(BaseModel):
    tenant_id: uuid.UUID
    plan: str
    api_calls_used: int
    api_calls_limit: int
    ai_tokens_used: int
    ai_tokens_limit: int
    cost_cents: int


class ErrorResponse(BaseModel):
    error: str
    message: str
    used: Optional[int] = None
    limit: Optional[int] = None
