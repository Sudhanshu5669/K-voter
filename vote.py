#!/usr/bin/env python3
"""
Karuta Top.gg Auto-Voter (Playwright edition - Robust)
Uses a real browser context with your session cookie so auth works exactly
as it does in your browser.

Required environment variable:
  TOPGG_SESSION_TOKEN  — value of the __Secure-authjs.session-token cookie
"""

import os
import sys
import time

VOTE_URL     = "https://top.gg/bot/646937666251915264/vote"
COOKIE_NAME  = "__Secure-authjs.session-token"
SESSION_ENV  = "TOPGG_SESSION_TOKEN"

# ── Timeout Config ────────────────────────────────────────────────────────
NAV_TIMEOUT  = 40_000   # page navigation (longer for slower runners)
BTN_TIMEOUT  = 20_000   # wait for elements to load/hydrate
POST_CLICK   = 8_000    # let the XHR/mutation finish after click


def main() -> None:
    # ── Read session token ─────────────────────────────────────────────────
    session_token = os.environ.get(SESSION_ENV, "").strip()
    if not session_token:
        print(f"[ERROR] '{SESSION_ENV}' env var is not set.")
        print(f"  Copy the value of {COOKIE_NAME} from top.gg DevTools → Application → Cookies.")
        sys.exit(1)

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    with sync_playwright() as pw:
        # Launch headless browser
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

        # ── Inject session cookie ──────────────────────────────────────────
        # We set both .top.gg and top.gg to ensure it matches perfectly
        ctx.add_cookies([
            {
                "name":     COOKIE_NAME,
                "value":    session_token,
                "domain":   "top.gg",
                "path":     "/",
                "secure":   True,
                "httpOnly": True,
                "sameSite": "Lax",
            },
            {
                "name":     COOKIE_NAME,
                "value":    session_token,
                "domain":   ".top.gg",
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
            # We wait for 'networkidle' so Next.js hydration/session fetching finishes
            page.goto(VOTE_URL, timeout=NAV_TIMEOUT, wait_until="networkidle")
        except PWTimeout:
            print("[WARN] Timed out waiting for network to be idle. Proceeding with DOM elements...")

        # Let the page hydrate/stabilize for an extra 3 seconds
        page.wait_for_timeout(3000)

        # ── Wait for either Vote or Login prompt to appear ───────────────
        print("[INFO] Waiting for page auth hydration...")
        
        # We look for the main vote button OR a login state to confirm where we are
        vote_button_selector = "button:has-text('Vote'), [data-testid='vote-button']"
        login_indicator_selector = "a:has-text('Login to vote'), button:has-text('Login to vote'), a:has-text('Login')"
        already_voted_selector = "text='Already voted', text='vote again in', text='Next vote'"

        try:
            page.locator(f"{vote_button_selector}, {login_indicator_selector}, {already_voted_selector}").first.wait_for(timeout=BTN_TIMEOUT)
        except PWTimeout:
            print("[WARN] Page elements didn't stabilize in time. Scanning DOM directly...")

        page_text = page.inner_text("body")

        # ── Check if we need to log in ─────────────────────────────────────
        # If the page still asks us to log in to vote, the cookie is invalid
        if "login to vote" in page_text.lower() or "sign in to vote" in page_text.lower():
            print("[ERROR] Not logged in — the session cookie was rejected by top.gg.")
            print("  Make sure you copied the correct __Secure-authjs.session-token value.")
            page.screenshot(path="login_failed.png")
            print("[INFO] Screenshot saved to 'login_failed.png'.")
            browser.close()
            sys.exit(1)

        # ── Check if we already voted ──────────────────────────────────────
        if any(kw in page_text.lower() for kw in ["already voted", "vote again in", "next vote"]):
            print("[SKIP] Already voted — next vote is not available yet.")
            browser.close()
            sys.exit(0)

        # ── Find the Vote button ───────────────────────────────────────────
        print("[INFO] Locating Vote button ...")
        vote_btn = None
        selectors = [
            "button:has-text('Vote')",
            "[data-testid='vote-button']",
            "button:has-text('vote')",
            "a:has-text('Vote')",
        ]
        
        for sel in selectors:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                vote_btn = loc
                break

        if vote_btn is None:
            print("[ERROR] Could not find the Vote button on the page.")
            page.screenshot(path="vote_btn_missing.png")
            print("[INFO] Screenshot saved to 'vote_btn_missing.png'.")
            print("  Page excerpt:", page_text[:600])
            browser.close()
            sys.exit(1)

        # ── Click vote ─────────────────────────────────────────────────────
        print("[INFO] Clicking Vote button ...")
        vote_btn.click()
        
        # Wait a bit longer to ensure requests complete
        print("[INFO] Waiting for vote processing...")
        page.wait_for_timeout(POST_CLICK)

        # ── Interpret result ───────────────────────────────────────────────
        if vote_result:
            error      = vote_result.get("error", "NONE")
            ack        = vote_result.get("isAcknowledged", False)
            new_count  = vote_result.get("newVoteCount", "?")
            captcha    = vote_result.get("captchaProvider")

            if captcha:
                print(f"[ERROR] Captcha triggered ({captcha}). Automatic voting is blocked by captcha.")
                page.screenshot(path="captcha_triggered.png")
                browser.close()
                sys.exit(1)

            if error and error != "NONE":
                print(f"[ERROR] Vote failed with GraphQL error: {error}")
                browser.close()
                sys.exit(1)

            if ack:
                print(f"[SUCCESS] ✅ Vote cast! Total Karuta votes: {new_count}")
            else:
                print(f"[WARN] Vote response not acknowledged: {vote_result}")
        else:
            # Check updated page text if GraphQL intercept missed it
            updated_text = page.inner_text("body")
            if any(kw in updated_text.lower() for kw in ["already voted", "vote again"]):
                print("[SUCCESS] ✅ Vote cast successfully!")
            elif "success" in updated_text.lower() or "thank" in updated_text.lower():
                print("[SUCCESS] ✅ Vote appears to have gone through successfully.")
            else:
                print("[WARN] Voted but could not confirm result. Check top.gg manually.")
                page.screenshot(path="vote_unconfirmed.png")

        browser.close()


if __name__ == "__main__":
    main()
