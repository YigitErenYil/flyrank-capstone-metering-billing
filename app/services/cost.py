from app.config import (
    PRICE_PER_API_CALL_CENTS,
    PRICE_PER_1K_INPUT_TOKENS_CENTS,
    PRICE_PER_1K_CACHED_INPUT_TOKENS_CENTS,
    PRICE_PER_1K_OUTPUT_TOKENS_CENTS,
)


def calculate_api_call_cost_cents() -> int:
    return PRICE_PER_API_CALL_CENTS


def calculate_ai_token_cost_cents(
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> int:
    """
    Token categories are priced SEPARATELY, never summed before pricing.
    Reasoning tokens are billed at the output rate, per the brief's rule.
    All math in integer cents; we price per-1000-token buckets using
    integer division at the end to avoid floats anywhere in the path.
    """
    input_cost = (input_tokens * PRICE_PER_1K_INPUT_TOKENS_CENTS) // 1000
    cached_cost = (cached_input_tokens * PRICE_PER_1K_CACHED_INPUT_TOKENS_CENTS) // 1000
    output_cost = (output_tokens * PRICE_PER_1K_OUTPUT_TOKENS_CENTS) // 1000
    reasoning_cost = (reasoning_tokens * PRICE_PER_1K_OUTPUT_TOKENS_CENTS) // 1000

    return input_cost + cached_cost + output_cost + reasoning_cost


def total_ai_tokens(input_tokens: int, cached_input_tokens: int, output_tokens: int, reasoning_tokens: int) -> int:
    """Total token quantity for quota purposes only — NOT for cost math (cost prices categories separately)."""
    return input_tokens + cached_input_tokens + output_tokens + reasoning_tokens
