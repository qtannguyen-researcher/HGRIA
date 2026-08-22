#!/usr/bin/env python3
"""Phase 3B measurement browser. Does not modify the HGRIA repository.

Opens /?evaluation=true against the local server and uses the real webcam.
Permission is auto-granted. Fake video devices are not used.
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

# / returns 404; /index.html is the local frontend. localhost (not 127.0.0.1)
# matches CSP connect-src 'self' used by webcam POST / Socket.IO.
URL = os.environ.get(
    "HGRIA_PHASE3B_URL",
    "http://localhost:5000/index.html?evaluation=true",
)
READY = os.environ.get("HGRIA_PHASE3B_BROWSER_READY", "/tmp/hgria-phase3b-browser.ready")
LOG = os.environ.get("HGRIA_PHASE3B_BROWSER_LOG", "/tmp/hgria-phase3b-browser.log")


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    if os.path.exists(READY):
        os.remove(READY)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = browser.new_context(
            permissions=["camera"],
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()
        page.on("console", lambda msg: _log(f"console:{msg.type}:{msg.text}"))
        page.on("pageerror", lambda err: _log(f"pageerror:{err}"))

        _log(f"goto {URL}")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        info = page.evaluate(
            """() => ({
                href: location.href,
                evaluation: new URLSearchParams(location.search).get('evaluation'),
                lastFrameId: (window.HGRIA_CLIENT_LOG && window.HGRIA_CLIENT_LOG.lastFrameId)
                    ? window.HGRIA_CLIENT_LOG.lastFrameId() : null,
                runId: (window.HGRIA_CLIENT_LOG && window.HGRIA_CLIENT_LOG.getRunId)
                    ? window.HGRIA_CLIENT_LOG.getRunId() : null,
                videoReady: !!(document.getElementById('camera-preview')
                    && document.getElementById('camera-preview').srcObject),
            })"""
        )
        _log(f"page_state {info}")
        with open(READY, "w", encoding="utf-8") as handle:
            handle.write(str(info) + "\n")

        while True:
            time.sleep(2)
            try:
                state = page.evaluate(
                    """() => ({
                        lastFrameId: (window.HGRIA_CLIENT_LOG && window.HGRIA_CLIENT_LOG.lastFrameId)
                            ? window.HGRIA_CLIENT_LOG.lastFrameId() : null,
                        runId: (window.HGRIA_CLIENT_LOG && window.HGRIA_CLIENT_LOG.getRunId)
                            ? window.HGRIA_CLIENT_LOG.getRunId() : null,
                        videoReady: !!(document.getElementById('camera-preview')
                            && document.getElementById('camera-preview').srcObject),
                    })"""
                )
                _log(f"heartbeat {state}")
            except Exception as exc:
                _log(f"heartbeat_error {exc}")
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
