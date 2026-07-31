#!/usr/bin/env python3
"""Drive a real Chromium browser through the HomeTV readiness flow."""

from __future__ import annotations

import argparse
import json
import time

from playwright.sync_api import sync_playwright


def wait_for_playback(page, timeout: int = 30_000) -> dict:
    page.wait_for_function(
        """
        () => {
          const video = document.querySelector('#video');
          return video && video.readyState >= 3 && !video.paused &&
                 video.currentTime > 0;
        }
        """,
        timeout=timeout,
    )
    first = page.locator("#video").evaluate(
        "video => ({time: video.currentTime, readyState: video.readyState})"
    )
    page.wait_for_timeout(3_000)
    second = page.locator("#video").evaluate(
        "video => ({time: video.currentTime, readyState: video.readyState})"
    )
    if second["time"] <= first["time"] + 1:
        raise RuntimeError(f"Browser video did not advance: {first} -> {second}")
    evidence = page.evaluate("window.__homeTVBufferEvidence")
    if not evidence["messages"]:
        raise RuntimeError("Playback started without reporting initial buffering")
    if not all(item["paused"] for item in evidence["messages"]):
        raise RuntimeError(f"Video played during initial buffering: {evidence}")
    target = evidence["messages"][-1]["target"]
    if max(item["seconds"] for item in evidence["messages"]) < target:
        raise RuntimeError(f"Playback began below the buffer threshold: {evidence}")
    return {"first": first, "second": second, "startup_buffer": evidence}


def assert_compensated_offset(session: dict) -> None:
    now = session["now"]
    compensated = now["playback_offset"] - now["elapsed"]
    target = session["initial_buffer_seconds"]
    if abs(compensated - target) > 1.5:
        raise RuntimeError(
            f"Session offset was not startup-buffer compensated: "
            f"{compensated:.3f}s versus {target:.3f}s"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:14243")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()

    session_responses = []
    browser_errors = []
    console_messages = []
    failed_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = browser.new_page()
        page.add_init_script(
            """
            window.__homeTVBufferEvidence = {messages: [], playedAt: null};
            document.addEventListener('DOMContentLoaded', () => {
              const message = document.querySelector('#message');
              const video = document.querySelector('#video');
              if (!message || !video) return;
              new MutationObserver(() => {
                const match = message.textContent.match(
                  /^Buffering .*: ([0-9.]+) \\/ ([0-9.]+) seconds$/
                );
                if (match) {
                  window.__homeTVBufferEvidence.messages.push({
                    seconds: Number(match[1]),
                    target: Number(match[2]),
                    paused: video.paused,
                    at: performance.now()
                  });
                }
              }).observe(message, {childList: true, subtree: true});
              video.addEventListener('play', () => {
                window.__homeTVBufferEvidence.playedAt = performance.now();
              });
            });
            """
        )
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_messages.append(
                f"{message.type}: {message.text}"
            ),
        )
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                f"{request.url}: {request.failure}"
            ),
        )

        def capture_session(response):
            if (
                response.request.method == "POST"
                and response.url.endswith("/api/watch/sessions")
                and response.ok
            ):
                session_responses.append(response.json())

        page.on("response", capture_session)
        management = page.goto(f"{args.base_url}/", wait_until="domcontentloaded")
        if management is None or not management.ok:
            raise RuntimeError("Management page did not load")
        page.wait_for_selector("#station-summary")

        watch = page.goto(f"{args.base_url}/watch", wait_until="domcontentloaded")
        if watch is None or not watch.ok:
            raise RuntimeError("Watch page did not load")
        page.wait_for_function(
            "() => document.querySelector('#channel-name')?.textContent === 'Fixture Blue'"
        )
        try:
            first_playback = wait_for_playback(page)
        except Exception:
            diagnostics = page.locator("#video").evaluate(
                """
                video => ({
                  currentTime: video.currentTime,
                  readyState: video.readyState,
                  networkState: video.networkState,
                  paused: video.paused,
                  error: video.error && {
                    code: video.error.code,
                    message: video.error.message
                  }
                })
                """
            )
            print(
                json.dumps(
                    {
                        "video": diagnostics,
                        "message": page.locator("#message").text_content(),
                        "sessions": session_responses,
                        "page_errors": browser_errors,
                        "console": console_messages,
                        "failed_requests": failed_requests,
                    },
                    indent=2,
                )
            )
            raise
        if not session_responses:
            raise RuntimeError("Browser did not create the first stream session")
        first_offset = session_responses[-1]["now"]["playback_offset"]
        assert_compensated_offset(session_responses[-1])
        if first_offset < 10:
            raise RuntimeError(f"Initial session restarted near zero: {first_offset}")
        session_count = len(session_responses)
        page.dispatch_event("#video", "waiting")
        page.wait_for_timeout(3_500)
        if len(session_responses) != session_count:
            raise RuntimeError("A transient waiting event recreated the HLS session")

        page.reload(wait_until="domcontentloaded")
        page.wait_for_function(
            "() => document.querySelector('#channel-name')?.textContent === 'Fixture Blue'"
        )
        refreshed_playback = wait_for_playback(page)
        if len(session_responses) < 2:
            raise RuntimeError("Refresh did not create a replacement stream session")
        refreshed_offset = session_responses[-1]["now"]["playback_offset"]
        assert_compensated_offset(session_responses[-1])
        if refreshed_offset <= first_offset + 2:
            raise RuntimeError(
                f"Refresh did not advance broadcast offset: "
                f"{first_offset} -> {refreshed_offset}"
            )

        page.evaluate(
            "window.__homeTVBufferEvidence = {messages: [], playedAt: null}"
        )
        page.select_option("#channels", "43")
        page.wait_for_function(
            "() => document.querySelector('#channel-name')?.textContent === 'Fixture Red'"
        )
        switched_playback = wait_for_playback(page)
        switched = session_responses[-1]
        if switched["now"]["channel_number"] != "43":
            raise RuntimeError(f"Channel switch created wrong session: {switched}")
        assert_compensated_offset(switched)

        failure_page = browser.new_page()
        failure_console = []
        failure_page.add_init_script(
            "window.HOMETV_STARTUP_TIMEOUT_SECONDS = 2"
        )
        failure_page.on(
            "console",
            lambda message: failure_console.append(message.text),
        )

        def require_impossible_buffer(route):
            response = route.fetch()
            body = response.json()
            body["initial_buffer_seconds"] = 100
            route.fulfill(response=response, json=body)

        failure_page.route(
            "**/api/watch/sessions",
            require_impossible_buffer,
        )
        failure_page.goto(f"{args.base_url}/watch", wait_until="domcontentloaded")
        for _ in range(50):
            if any(
                "Startup buffering timed out" in item
                for item in failure_console
            ):
                break
            failure_page.wait_for_timeout(200)
        if not any("Startup buffering timed out" in item for item in failure_console):
            raise RuntimeError("Startup timeout did not produce a clear error")
        failure_page.close()

        result = {
            "management_status": management.status,
            "watch_status": watch.status,
            "first_offset": first_offset,
            "refreshed_offset": refreshed_offset,
            "switched_channel": switched["now"]["channel_number"],
            "first_playback": first_playback,
            "refreshed_playback": refreshed_playback,
            "switched_playback": switched_playback,
            "browser_errors": browser_errors,
            "console": console_messages,
            "failed_requests": failed_requests,
            "startup_timeout": "passed",
            "checked_at": time.time(),
        }
        print(json.dumps(result, indent=2))
        browser.close()
    if browser_errors:
        raise RuntimeError(f"Browser page errors occurred: {browser_errors}")


if __name__ == "__main__":
    main()
