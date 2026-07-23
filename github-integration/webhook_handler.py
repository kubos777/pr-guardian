"""PR Guardian - GitHub Webhook Handler"""

import logging

logger = logging.getLogger(__name__)


def handle_webhook(payload: dict):
    """Handle incoming GitHub webhook events.

    Currently logs the event for traceability. Processing logic
    (diff fetching, agent invocation) will be added in a future iteration.
    """
    action = payload.get("action", "unknown")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number", "?")
    pr_title = pr.get("title", "untitled")
    repo = payload.get("repository", {}).get("full_name", "unknown/repo")

    logger.info(f"[Handler] PR #{pr_number} ({action}) in {repo}: \"{pr_title}\"")
    logger.info("[Handler] No processing yet — agent integration pending")
