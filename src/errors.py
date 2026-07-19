"""Application-level failures exposed by the LLM and orchestration layers."""


class LLMError(RuntimeError):
    """Base class for expected model-provider failures."""


class LLMUnavailableError(LLMError):
    """The model could not be reached after bounded retries."""


class LLMContextLimitError(LLMError):
    """The prepared prompt exceeds the configured or provider context limit."""


class LLMRefusalError(LLMError):
    """The model declined to answer the request."""


class LLMInvalidResponseError(LLMError):
    """The model response did not satisfy the structured-output contract."""


class SessionConflictError(ValueError):
    """A session ID was previously associated with a different CSV file."""
