#!/usr/bin/env python3
"""Guided demo driver for PR Guardian — for screen recording.

Opens a real browser and walks through the full flow hands-free while you
screen-record (Cmd+Shift+5 on macOS):

  1. Opens the demo PR on GitHub (shows the intentional bugs).
  2. Opens the PR Guardian dashboard.
  3. Fires a signed webhook (real HMAC) to trigger the pipeline.
  4. Watches the dashboard update live through the stages until COMPLETED.
  5. Opens the PR reviews tab to show the inline comments.

Usage:
    # Install once:
    uv run playwright install chromium

    # Against production:
    BASE_URL=https://54.90.206.50.nip.io \
    GITHUB_WEBHOOK_SECRET=<secret> \
    uv run python scripts/demo_playwright.py

    # Against local (docker compose up + dashboard on :3000):
    BASE_URL=http://localhost:3000 WEBHOOK_URL=http://localhost:8000 \
    GITHUB_WEBHOOK_SECRET=<secret> \
    uv run python scripts/demo_playwright.py

Env vars:
    BASE_URL              dashboard URL (default https://54.90.206.50.nip.io)
    WEBHOOK_URL           webhook base (default = BASE_URL; on prod the /webhook
                          path is proxied by Caddy so BASE_URL works)
    GITHUB_WEBHOOK_SECRET required, to sign the webhook
    DEMO_REPO             default kubos777/pr-guardian-demo
    DEMO_PR               default 1
    DEMO_HEAD_SHA         default the demo PR head sha
    DEMO_REPO_ID          default 1310435951
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "https://54.90.206.50.nip.io").rstrip("/")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", BASE_URL).rstrip("/")
SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
REPO = os.environ.get("DEMO_REPO", "kubos777/pr-guardian-demo")
PR = int(os.environ.get("DEMO_PR", "1"))
HEAD_SHA = os.environ.get("DEMO_HEAD_SHA", "be616779374e8553c61472628fca098dd2b15e45")
REPO_ID = int(os.environ.get("DEMO_REPO_ID", "1310435951"))

PR_URL = f"https://github.com/{REPO}/pull/{PR}"
REVIEWS_URL = f"{PR_URL}/files"


def fire_webhook() -> None:
    owner, name = REPO.split("/", 1)
    payload = {
        "action": "opened",
        "number": PR,
        "pull_request": {
            "number": PR,
            "title": "feat: add user features",
            "user": {"login": owner},
            "head": {"ref": "ft/add-user-features", "sha": HEAD_SHA},
            "base": {"ref": "main"},
        },
        "repository": {"id": REPO_ID, "full_name": REPO, "name": name, "owner": {"login": owner}},
        "sender": {"login": owner},
    }
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        f"{WEBHOOK_URL}/webhook",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
            "X-GitHub-Delivery": f"demo-{int(time.time())}",
            "X-Hub-Signature-256": sig,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("  webhook ->", r.status, r.read().decode())


HEADLESS = os.environ.get("HEADLESS", "0") == "1"


def pause(page, seconds: float, msg: str) -> None:
    print(f"  · {msg}", flush=True)
    page.wait_for_timeout(int(seconds * 1000))


def main() -> None:
    if not SECRET:
        raise SystemExit("Set GITHUB_WEBHOOK_SECRET")

    with sync_playwright() as p:
        # slow_mo paces each action so it's visible on the recording.
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 600)
        # Fixed 1440x900 viewport = consistent frame for recording (more
        # reliable on macOS than --start-maximized).
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()

        # 1. Show the PR with intentional bugs
        print("1) Abriendo el PR con bugs en GitHub...", flush=True)
        page.goto(PR_URL, wait_until="domcontentloaded", timeout=45000)
        page.bring_to_front()
        pause(page, 6, "Recorre el diff: secret hardcodeado, N+1, any, etc.")

        # 2. Open the dashboard
        print("2) Abriendo el dashboard...", flush=True)
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
        pause(page, 4, "Estado actual del dashboard")

        # 3. Trigger the pipeline
        print("3) Disparando el webhook (pipeline real)...", flush=True)
        fire_webhook()

        # 4. Watch it go live — reload once then let the dashboard poll
        print("4) Esperando que el dashboard muestre el análisis en vivo...", flush=True)
        page.reload(wait_until="domcontentloaded", timeout=45000)
        try:
            # Findings render as file:line code chips; wait for the critical one.
            page.wait_for_selector("text=Hardcoded Secret", timeout=60000)
            print("   findings visibles", flush=True)
        except Exception:
            print("   (no apareció el finding a tiempo; sigue de todas formas)", flush=True)
        pause(page, 5, "Muestra el score, el stepper y los findings")

        # 5. Show the inline comments on GitHub
        print("5) Abriendo los comentarios inline en GitHub...", flush=True)
        page.goto(REVIEWS_URL, wait_until="domcontentloaded", timeout=45000)
        pause(page, 8, "Scroll por los comentarios inline de PR Guardian")

        print("\nDemo terminada. Cierra el browser cuando termines de grabar.", flush=True)
        pause(page, 8, "Ventana abierta para el cierre de la grabación")
        browser.close()


if __name__ == "__main__":
    main()
