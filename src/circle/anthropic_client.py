"""Thin async wrapper around the Anthropic Messages API.

Adds exponential backoff (PRD section 4.8) and centralizes the model + token
defaults from PRD sections 3.1 and 3.3 so the rest of the bot doesn't have to
think about them.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Iterable

from anthropic import APIError, APIStatusError, AsyncAnthropic

logger = logging.getLogger(__name__)


# PRD section 3.1: facilitator AI configuration parameters.
FACILITATOR_TEMPERATURE = 0.7
FACILITATOR_MAX_TOKENS = 500

# PRD section 3.3: synthesis AI configuration parameters.
# Token budget bumped from 2000 → 4000 to fit the by-question structure
# (headline + participation map + per-Q where-it-lands/splits/outliers +
# cross-cutting + closing questions) without truncation.
# Temperature is None (omitted from the API call) because Opus 4.7 — the
# default synthesis model — deprecates `temperature`. Synthesis is meant to
# be deterministic-ish anyway; the model's default sampling is fine.
SYNTHESIS_TEMPERATURE: float | None = None
SYNTHESIS_MAX_TOKENS = 4000

# Proposal mode configuration. Larger token budget than synthesis because
# the output includes a draft proposal (per sub-question), rationale, vote
# signals (one per participant), outstanding tensions, and optional
# alternative drafts.
PROPOSAL_TEMPERATURE: float | None = None
PROPOSAL_MAX_TOKENS = 5000

# Permissions extraction (PRD section 3.2) — short JSON output, low temperature.
EXTRACTION_TEMPERATURE = 0.2
EXTRACTION_MAX_TOKENS = 600


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


class AnthropicClient:
    def __init__(self, api_key: str, default_model: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def complete(
        self,
        *,
        system: str,
        messages: Iterable[ChatMessage],
        model: str | None = None,
        temperature: float | None = FACILITATOR_TEMPERATURE,
        max_tokens: int = FACILITATOR_MAX_TOKENS,
        max_retries: int = 3,
    ) -> str:
        """Run a Messages API call and return the assistant text.

        Retries with exponential backoff on transient errors (network blips,
        5xx, rate limits). Re-raises on the final failure so the caller can
        send the participant the PRD section 4.8 fallback message.

        Pass `temperature=None` to omit the temperature parameter entirely —
        required for newer models (e.g. Opus 4.7) that have deprecated it.
        """
        payload_messages = [{"role": m.role, "content": m.content} for m in messages]
        chosen_model = model or self._default_model

        request_kwargs: dict = {
            "model": chosen_model,
            "system": system,
            "messages": payload_messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            request_kwargs["temperature"] = temperature

        backoff_seconds = 1.0
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await self._client.messages.create(**request_kwargs)
            except APIStatusError as exc:
                last_error = exc
                # 4xx (other than 408/429) is a programmer error — don't retry.
                status = getattr(exc, "status_code", None)
                if status is not None and 400 <= status < 500 and status not in (408, 429):
                    logger.error(
                        "anthropic 4xx status=%s on attempt %s: %s",
                        status,
                        attempt,
                        exc,
                    )
                    raise
                logger.warning(
                    "anthropic transient status=%s on attempt %s/%s: %s",
                    status,
                    attempt,
                    max_retries,
                    exc,
                )
            except APIError as exc:
                last_error = exc
                logger.warning(
                    "anthropic APIError on attempt %s/%s: %s",
                    attempt,
                    max_retries,
                    exc,
                )

            else:
                text_parts: list[str] = []
                for block in response.content:
                    text = getattr(block, "text", None)
                    if text:
                        text_parts.append(text)
                return "".join(text_parts).strip()

            if attempt < max_retries:
                await asyncio.sleep(backoff_seconds)
                backoff_seconds *= 2

        assert last_error is not None
        print(
            f"anthropic call failed after {max_retries} attempts: {last_error}",
            file=sys.stderr,
        )
        raise last_error
