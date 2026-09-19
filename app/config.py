import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://billing:billing@db:5432/billing")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

FRONTEND_SUCCESS_URL = os.getenv("FRONTEND_SUCCESS_URL", "http://localhost:8000/billing/success")
FRONTEND_CANCEL_URL = os.getenv("FRONTEND_CANCEL_URL", "http://localhost:8000/billing/cancel")

# --- Pricing constants (pinned, cents/micro-units — never floats) ---
# All prices in cents per unit unless noted.
PRICE_PER_API_CALL_CENTS = 1  # $0.01 per API call

# AI token pricing — per 1000 tokens, in cents. Cached input is cheaper.
# Reasoning tokens are billed at the OUTPUT rate (per brief's pricing rule).
PRICE_PER_1K_INPUT_TOKENS_CENTS = 3        # $0.03 / 1k input tokens
PRICE_PER_1K_CACHED_INPUT_TOKENS_CENTS = 1  # $0.01 / 1k cached input tokens (cheaper)
PRICE_PER_1K_OUTPUT_TOKENS_CENTS = 6         # $0.06 / 1k output tokens
# reasoning tokens use PRICE_PER_1K_OUTPUT_TOKENS_CENTS, not a separate constant

PLAN_QUOTAS = {
    "free": {"api_calls": 1000, "ai_tokens": 100_000},
    "pro": {"api_calls": 10_000, "ai_tokens": 1_000_000},
}
