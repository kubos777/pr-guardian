"""Deterministic fingerprints used to prevent duplicate review comments.

A finding fingerprint identifies "this exact issue, on this exact line, at
this exact head_sha" independent of any job/retry bookkeeping, so retried
or re-delivered work never produces a second GitHub comment for the same
thing (requirement #15). The fingerprint-set hash identifies "this exact
batch of findings", embedded as a hidden marker in the published review
body so a retried publish can recognize its own prior success even if it
lost the HTTP response.
"""

from __future__ import annotations

import hashlib


def finding_fingerprint(
    *, repository_id: int, pr_number: int, head_sha: str, rule_id: str, path: str, line: int, message: str
) -> str:
    normalized_message = " ".join(message.split()).strip().lower()
    payload = f"{repository_id}:{pr_number}:{head_sha}:{rule_id}:{path}:{line}:{normalized_message}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_set_hash(fingerprints: list[str]) -> str:
    joined = ",".join(sorted(fingerprints))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


MARKER_PREFIX = "pr-guardian:fingerprint-set:"


def embed_marker(body: str, fp_set_hash: str) -> str:
    return f"{body}\n\n<!-- {MARKER_PREFIX}{fp_set_hash} -->"


def extract_marker(body: str) -> str | None:
    idx = body.find(MARKER_PREFIX)
    if idx == -1:
        return None
    tail = body[idx + len(MARKER_PREFIX) :]
    end = tail.find("-->")
    return tail[:end].strip() if end != -1 else tail.strip()
