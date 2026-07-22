"""PR Guardian - GitHub Webhook Server"""

import hashlib
import hmac
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Request, abort, jsonify, request

from webhook_handler import handle_webhook

# Load environment variables
env_path = Path(__file__).resolve().parent.parent
load_dotenv(env_path / ".env")
load_dotenv(env_path / ".env.local", override=True)

# Configuration
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "3000"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").upper()

# Logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def verify_signature(req: Request) -> bool:
    """Verify the GitHub webhook signature (X-Hub-Signature-256)."""
    signature_header = req.headers.get("X-Hub-Signature-256")
    if not signature_header:
        logger.warning("Missing X-Hub-Signature-256 header")
        return False

    if not WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET not configured")
        return False

    expected_signature = "sha256=" + hmac.HMAC(
        key=WEBHOOK_SECRET.encode("utf-8"),
        msg=req.get_data(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)


@app.route("/webhook", methods=["POST"])
def webhook():
    """POST /webhook — Receive GitHub webhook events."""
    # Verify signature
    if not verify_signature(request):
        logger.warning("Invalid webhook signature — rejecting request")
        abort(401, description="Invalid signature")

    # Parse event
    event_type = request.headers.get("X-GitHub-Event", "unknown")
    delivery_id = request.headers.get("X-GitHub-Delivery", "no-id")
    payload = request.get_json(silent=True)

    if payload is None:
        logger.warning("Empty or invalid JSON payload")
        abort(400, description="Invalid JSON payload")

    logger.info(f"Received event: {event_type} (delivery: {delivery_id})")
    logger.debug(f"Payload:\n{json.dumps(payload, indent=2)}")

    # TODO: process events asynchronously in a future iteration
    # For now, acknowledge immediately without processing
    return jsonify({"status": "received", "event": event_type}), 200


@app.route("/health", methods=["GET"])
def health():
    """GET /health — Basic health check."""
    return jsonify({"status": "ok", "service": "pr-guardian-webhook"}), 200


def start_server():
    """Start the webhook server."""
    if not WEBHOOK_SECRET:
        logger.error("GITHUB_WEBHOOK_SECRET is not set. Exiting.")
        sys.exit(1)

    logger.info(f"Starting PR Guardian webhook server on {SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=(LOG_LEVEL == "DEBUG"))


if __name__ == "__main__":
    start_server()
