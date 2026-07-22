"""Pipeline-wide retry classification.

Every external call in the review pipeline (GitHub fetch, LLM, GitHub
publish) gets mapped to exactly one of these two. Celery's
``autoretry_for`` is configured against ``RetryableError`` only — anything
else (``NonRetryableError``, or a bug) fails the task on the first
attempt (requirement #12).
"""


class RetryableError(Exception):
    """Timeout / 429 / 5xx / malformed structured output — retry with backoff+jitter."""


class NonRetryableError(Exception):
    """401/403 or a deterministic validation failure — fail immediately, no retry."""
