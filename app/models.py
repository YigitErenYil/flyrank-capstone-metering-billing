import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def uuid_pk():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now_utc():
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id = uuid_pk()
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_utc)

    subscription = relationship("Subscription", back_populates="tenant", uselist=False)
    usage_events = relationship("UsageEvent", back_populates="tenant")


class Plan(Base):
    __tablename__ = "plans"

    id = Column(String, primary_key=True)  # 'free' | 'pro'
    name = Column(String, nullable=False)
    monthly_api_calls = Column(Integer, nullable=False)
    monthly_ai_tokens = Column(Integer, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = uuid_pk()
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True)
    plan_id = Column(String, ForeignKey("plans.id"), nullable=False, default="free")
    status = Column(String, nullable=False, default="active")  # active | past_due | canceled
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    current_period_start = Column(DateTime(timezone=True), default=now_utc)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    tenant = relationship("Tenant", back_populates="subscription")
    plan = relationship("Plan")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_usage_events_idempotency_key"),
    )

    id = uuid_pk()
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    type = Column(String, nullable=False)  # 'api_call' | 'ai_tokens'
    quantity = Column(Integer, nullable=False)  # for api_call: 1, for ai_tokens: total tokens
    idempotency_key = Column(String, nullable=False)

    input_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)

    cost_cents = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=now_utc)

    tenant = relationship("Tenant", back_populates="usage_events")


class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"

    id = uuid_pk()
    stripe_event_id = Column(String, nullable=False, unique=True)
    processed_at = Column(DateTime(timezone=True), default=now_utc)
