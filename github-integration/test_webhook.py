"""Quick script to test the /webhook endpoint with a mock pull_request.opened payload."""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load secrets
env_path = Path(__file__).resolve().parent.parent
load_dotenv(env_path / ".env.local")

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
SERVER_URL = "http://localhost:8080/webhook"

# Mock payload: pull_request.opened
payload = {
    "action": "opened",
    "number": 7,
    "pull_request": {
        "id": 123456789,
        "number": 7,
        "title": "feat: add user validation",
        "user": {"login": "dev-user"},
        "head": {"ref": "ft/user-validation", "sha": "abc123"},
        "base": {"ref": "main", "sha": "def456"},
        "body": "Added input validation for user endpoints",
        "diff_url": "https://github.com/owner/repo/pull/7.diff",
    },
    "repository": {
        "full_name": "owner/pr-guardian",
        "html_url": "https://github.com/owner/pr-guardian",
    },
    "sender": {"login": "dev-user"},
}

# Serialize payload
body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

# Generate HMAC signature
signature = "sha256=" + hmac.HMAC(
    key=WEBHOOK_SECRET.encode("utf-8"),
    msg=body,
    digestmod=hashlib.sha256,
).hexdigest()

# Send request
headers = {
    "Content-Type": "application/json",
    "X-GitHub-Event": "pull_request",
    "X-GitHub-Delivery": "test-delivery-001",
    "X-Hub-Signature-256": signature,
}

print(f"Sending mock pull_request.opened to {SERVER_URL}")
print(f"Signature: {signature[:30]}...")

try:
    response = requests.post(SERVER_URL, data=body, headers=headers)
    print(f"\nResponse: {response.status_code}")
    print(f"Body: {json.dumps(response.json(), indent=2)}")
except requests.ConnectionError:
    print("\nERROR: Could not connect. Is the server running?")
    print(f"  Start it with: python server.py")
    sys.exit(1)
