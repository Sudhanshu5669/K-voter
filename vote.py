#!/usr/bin/env python3
"""
Karuta Top.gg Auto-Voter (Playwright edition)
Uses a real browser context with your session cookie so auth works exactly
as it does in your browser — no header/cookie guessing needed.

Required environment variable:
  TOPGG_SESSION_TOKEN  — value of the __Secure-authjs.session-token cookie
"""

import os
import sys
import time

VOTE_URL     = "https://top.gg/bot/646937666251915264/vote"
COOKIE_NAME  = "__Secure-authjs.session-token"
SESSION_ENV  = "TOPGG_SESSION_TOKEN"

# ── How long (ms) to wait for various page events ─────────────────────────
NAV_TIMEOUT  = 30_000   # page navigation
BTN_TIMEOUT  = 15_000   # vote button to appear
POST_CLICK   = 5_000    # settle after click


def main() -> None:
    # ── Read session token ─────────────────────────────────────────────────
    session_token = os.environ.get(SESSION_ENV, "").strip()
    if not session_token:
        print(f"[ERROR] '{SESSION_ENV}' env var is not set.")
        print(f"  Copy the value of {COOKIE_NAME} from top.gg DevTools → Application → Cookies.")
        sys.exit(1)

    # Import here so missing dep gives a clear message
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            )
        )

        # ── Inject session cookie ──────────────────────────────────────────
        ctx.add_cookies([
            {
                "name":     COOKIE_NAME,
                "value":    session_token,
                "domain":   "top.gg",
                "path":     "/",
                "secure":   True,
                "httpOnly": True,
                "sameSite": "Lax",
            }
        ])

        page = ctx.new_page()

        # ── Intercept the GraphQL vote response ───────────────────────────
        vote_result: dict = {}

        def on_response(response):
            if "api.top.gg/graphql" in response.url:
                try:
                    body = response.json()
                    ve = (body.get("data") or {}).get("voteEntity")
                    if ve is not None:
                        vote_result.update(ve)
                except Exception:
                    pass

        page.on("response", on_response)

        # ── Navigate to vote page ──────────────────────────────────────────
        print(f"[INFO] Loading {VOTE_URL} ...")
        try:
            page.goto(VOTE_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        except PWTimeout:
            print("[ERROR] Timed out loading the vote page.")
            browser.close()
            sys.exit(1)

        # ── Check we're logged in ──────────────────────────────────────────
        # If the cookie is invalid, top.gg redirects to a login page or
        # shows a "sign in to vote" prompt instead of the vote button.
        page_text = page.inner_text("body")
        if any(kw in page_text.lower() for kw in ["sign in", "log in", "login to vote"]):
            print("[ERROR] Not logged in — the session cookie is invalid or expired.")
            print("  Re-copy __Secure-authjs.session-token from top.gg and update the GitHub secret.")
            browser.close()
            sys.exit(1)

        # ── Find the Vote button ───────────────────────────────────────────
        print("[INFO] Looking for the Vote button ...")
        vote_btn = None
        selectors = [
            "button:has-text('Vote')",
            "a:has-text('Vote')",
            "[data-testid='vote-button']",
            "button:has-text('vote')",
        ]
        try:
            for sel in selectors:
                locator = page.locator(sel).first
                if locator.count() > 0:
                    locator.wait_for(timeout=BTN_TIMEOUT)
                    vote_btn = locator
                    break
        except PWTimeout:
            pass

        if vote_btn is None:
            # Already voted? Check for "already voted" text
            if any(kw in page_text.lower() for kw in ["already voted", "vote again in", "next vote"]):
                print("[SKIP] Already voted — next vote not available yet.")
                browser.close()
                sys.exit(0)
            print("[ERROR] Could not find the Vote button on the page.")
            print("  Page excerpt:", page_text[:400])
            browser.close()
            sys.exit(1)

        # ── Click vote ─────────────────────────────────────────────────────
        print("[INFO] Clicking Vote button ...")
        vote_btn.click()
        page.wait_for_timeout(POST_CLICK)   # let the XHR complete

        # ── Interpret result ───────────────────────────────────────────────
        if vote_result:
            error      = vote_result.get("error", "NONE")
            ack        = vote_result.get("isAcknowledged", False)
            new_count  = vote_result.get("newVoteCount", "?")
            captcha    = vote_result.get("captchaProvider")

            if captcha:
                print(f"[ERROR] Captcha triggered ({captcha}). Cannot vote automatically right now.")
                browser.close()
                sys.exit(1)

            if error and error != "NONE":
                print(f"[ERROR] Vote failed: {error}")
                browser.close()
                sys.exit(1)

            if ack:
                print(f"[SUCCESS] ✅ Vote cast! Total Karuta votes: {new_count}")
            else:
                print(f"[WARN] Vote response not acknowledged: {vote_result}")
        else:
            # No GraphQL response intercepted — check page for feedback
            updated_text = page.inner_text("body")
            if any(kw in updated_text.lower() for kw in ["already voted", "vote again"]):
                print("[SKIP] Already voted — next vote not available yet.")
            elif "success" in updated_text.lower() or "thank" in updated_text.lower():
                print("[SUCCESS] ✅ Vote appears to have gone through (no GraphQL response captured).")
            else:
                print("[WARN] Voted but could not confirm result from page. Check top.gg manually.")

        browser.close()


if __name__ == "__main__":
    main()
