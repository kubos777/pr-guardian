"""Domain exceptions for the analysis brain.

Kept free of any Celery/worker knowledge on purpose: agent-core is "the
brain" and should be usable/testable standalone. ``worker/tasks.py`` is the
only place that translates these into ``RetryableError`` /
``NonRetryableError`` for the pipeline's retry policy.
"""


class LLMTransientError(Exception):
    """Timeout, 429, 5xx, or malformed structured output — worth retrying."""


class LLMFatalError(Exception):
    """401/403 or another non-retryable LLM API failure."""


class DiffValidationError(Exception):
    """A finding does not correspond to an actual line in the current diff."""
