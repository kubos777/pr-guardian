"""Job stage enum shared by the webhook ingress, the worker and the store.

This is the single source of truth for the state machine named in
ARCHITECTURE_DIAGRAMS.md. Every job moves through these stages left to
right; FAILED is reachable from any in-flight stage.
"""

from __future__ import annotations

from enum import Enum


class Stage(str, Enum):
    RECEIVED = "RECEIVED"
    QUEUED = "QUEUED"
    FETCHING_CONTEXT = "FETCHING_CONTEXT"
    ANALYZING = "ANALYZING"
    VALIDATING = "VALIDATING"
    POSTING_TO_GITHUB = "POSTING_TO_GITHUB"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_STAGES = {Stage.COMPLETED, Stage.FAILED}

# Stages that call an external, transiently-failing service and therefore
# have a retry policy (requirement #12). VALIDATING is deterministic
# (Pydantic + diff cross-check) and is intentionally excluded: a validation
# failure is not retried.
RETRYABLE_STAGES = {Stage.FETCHING_CONTEXT, Stage.ANALYZING, Stage.POSTING_TO_GITHUB}
