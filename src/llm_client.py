"""Resilient adapter around OpenAI structured responses."""

import time
from typing import TypeVar

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from .config import settings
from .errors import (
    LLMContextLimitError,
    LLMInvalidResponseError,
    LLMRefusalError,
    LLMUnavailableError,
)

T = TypeVar("T", bound=BaseModel)
_CONTEXT_ERROR_MARKERS = ("context length", "too many tokens", "maximum context")


class LLMClient:
    """Makes typed model calls with bounded latency and failure classification."""

    def __init__(self) -> None:
        self.model = settings.openai_model
        self.client = (
            OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
            if settings.openai_api_key
            else None
        )
        self.last_latency_seconds: float | None = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def structured(self, system_prompt: str, user_prompt: str, schema: type[T]) -> T:
        if not self.client:
            raise LLMUnavailableError("OPENAI_API_KEY is not configured.")

        approximate_tokens = (len(system_prompt) + len(user_prompt)) // 4
        if approximate_tokens > settings.max_context_tokens:
            raise LLMContextLimitError(
                f"Prepared prompt is approximately {approximate_tokens:,} tokens; "
                f"the configured limit is {settings.max_context_tokens:,}."
            )

        last_error: Exception | None = None
        for attempt in range(settings.max_retries):
            started_at = time.monotonic()
            try:
                response = self.client.responses.parse(
                    model=self.model,
                    instructions=system_prompt,
                    input=user_prompt,
                    text_format=schema,
                    max_output_tokens=settings.max_output_tokens,
                )
                self.last_latency_seconds = time.monotonic() - started_at
                parsed = response.output_parsed
                if parsed is not None:
                    return schema.model_validate(parsed)

                refusal = self._find_refusal(response)
                if refusal:
                    raise LLMRefusalError(refusal)
                incomplete = getattr(response, "incomplete_details", None)
                if incomplete:
                    raise LLMInvalidResponseError(f"Model response was incomplete: {incomplete}")
                raise LLMInvalidResponseError("Model returned no structured output.")
            except LLMRefusalError:
                raise
            except LLMInvalidResponseError:
                raise
            except BadRequestError as error:
                if any(marker in str(error).lower() for marker in _CONTEXT_ERROR_MARKERS):
                    raise LLMContextLimitError(str(error)) from error
                raise LLMInvalidResponseError(f"Provider rejected the structured request: {error}") from error
            except (ValidationError, TypeError, ValueError) as error:
                raise LLMInvalidResponseError(f"Structured output validation failed: {error}") from error
            except (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError) as error:
                last_error = error
                if attempt + 1 < settings.max_retries:
                    time.sleep(settings.retry_base_delay * (2**attempt))
            except APIStatusError as error:
                raise LLMUnavailableError(f"Model provider returned HTTP {error.status_code}.") from error

        raise LLMUnavailableError(
            f"Model unavailable after {settings.max_retries} attempts: {last_error}"
        )

    @staticmethod
    def _find_refusal(response: object) -> str | None:
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "refusal":
                    return getattr(content, "refusal", None) or "The model refused this request."
        return None
