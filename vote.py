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

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    sync_playwright = None
    PWTimeout = None

VOTE_URL     = "https://top.gg/bot/646937666251915264/vote"
COOKIE_NAME  = "__Secure-authjs.session-token"
SESSION_ENV  = "TOPGG_SESSION_TOKEN"

# ── Timeout Config ────────────────────────────────────────────────────────
NAV_TIMEOUT  = 40_000   # page navigation (longer for slower runners)
BTN_TIMEOUT  = 20_000   # wait for elements to load/hydrate
POST_CLICK   = 8_000    # let the XHR/mutation finish after click


def run_vote_attempt(session_token: str, attempt: int, max_retries: int) -> tuple[bool, str]:
    """
    Performs a single voting attempt.
    Returns a tuple: (success_or_skip, result_type)
    """
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
        
        try:
            # Simply wait for the main Next.js div or page content to hydrate
            page.wait_for_selector("#__next, body", timeout=BTN_TIMEOUT)
        except PWTimeout:
            print("[WARN] Page elements didn't stabilize in time. Scanning DOM directly...")

        # ── Find and wait for the Vote button ────────────────────────────────
        print("[INFO] Waiting for Vote button or status to hydrate...")
        vote_btn = None
        selectors = [
            "button:has-text('Vote')",
            "[data-testid='vote-button']",
            "button:has-text('vote')",
            "a:has-text('Vote')",
        ]

        # We will poll for up to 45 seconds to allow ads / hydration to complete
        max_wait_seconds = 45
        start_time = time.time()
        last_logged_countdown = None
        
        while time.time() - start_time < max_wait_seconds:
            current_text = page.inner_text("body")
            current_text_lower = current_text.lower()
            
            # 1. Check if session expired / not logged in
            if "login to vote" in current_text_lower or "sign in to vote" in current_text_lower:
                print("[ERROR] Not logged in — the session cookie was rejected by top.gg.")
                print("  Make sure you copied the correct __Secure-authjs.session-token value.")
                page.screenshot(path="login_failed.png")
                print("[INFO] Screenshot saved to 'login_failed.png'.")
                browser.close()
                return False, "LOGIN_FAILED"

            # 2. Check if we already voted
            if any(kw in current_text_lower for kw in ["already voted", "vote again in", "next vote"]):
                print("[SKIP] Already voted — next vote is not available yet.")
                browser.close()
                return True, "ALREADY_VOTED"
            
            # 3. Check and log ad countdown
            if "you will be able to vote after this ad" in current_text_lower:
                lines = current_text.split("\n")
                countdown_val = None
                for idx, line in enumerate(lines):
                    if "you will be able to vote after this ad" in line.lower():
                        if idx + 1 < len(lines):
                            next_line = lines[idx+1].strip()
                            if next_line.isdigit():
                                countdown_val = int(next_line)
                                break
                
                if countdown_val is not None:
                    if countdown_val != last_logged_countdown:
                        print(f"[INFO] Ad is active. Waiting for ad to finish ({countdown_val}s remaining)...")
                        last_logged_countdown = countdown_val
                else:
                    if last_logged_countdown is None:
                        print("[INFO] Ad is active. Waiting for ad to finish...")
                        last_logged_countdown = -1
            
            # 4. Search for visible and active vote button
            for sel in selectors:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    if not loc.is_disabled():
                        vote_btn = loc
                        break
                    else:
                        print(f"[INFO] Vote button found via '{sel}' but it is currently disabled (waiting for ad/hydration)...")
            
            if vote_btn is not None:
                break
                
            page.wait_for_timeout(2000)

        if vote_btn is None:
            print("[ERROR] Could not find the Vote button on the page.")
            page.screenshot(path="vote_btn_missing.png")
            print("[INFO] Screenshot saved to 'vote_btn_missing.png'.")
            print("  Page excerpt:", page.inner_text("body")[:800])
            browser.close()
            return False, "NO_VOTE_BUTTON"

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
                screenshot_filename = f"captcha_triggered_attempt_{attempt}.png"
                page.screenshot(path=screenshot_filename)
                print(f"[INFO] Screenshot saved to '{screenshot_filename}'.")
                browser.close()
                return False, "CAPTCHA"

            if error and error != "NONE":
                if error == "USER_ALREADY_VOTED" or "already" in error.lower():
                    print(f"[SKIP] Already voted — next vote is not available yet (GraphQL error: {error}).")
                    browser.close()
                    return True, "ALREADY_VOTED"
                print(f"[ERROR] Vote failed with GraphQL error: {error}")
                browser.close()
                return False, "VOTE_FAILED"

            if ack:
                print(f"[SUCCESS] ✅ Vote cast! Total Karuta votes: {new_count}")
                browser.close()
                return True, "SUCCESS"
            else:
                print(f"[WARN] Vote response not acknowledged: {vote_result}")
                browser.close()
                return True, "UNCONFIRMED"
        else:
            # Check updated page text if GraphQL intercept missed it
            updated_text = page.inner_text("body")
            if any(kw in updated_text.lower() for kw in ["already voted", "vote again"]):
                print("[SUCCESS] ✅ Vote cast successfully!")
                browser.close()
                return True, "SUCCESS"
            elif "success" in updated_text.lower() or "thank" in updated_text.lower():
                print("[SUCCESS] ✅ Vote appears to have gone through successfully.")
                browser.close()
                return True, "SUCCESS"
            else:
                print("[WARN] Voted but could not confirm result. Check top.gg manually.")
                page.screenshot(path="vote_unconfirmed.png")
                browser.close()
                return True, "UNCONFIRMED"


def main() -> None:
    # ── Read session token ─────────────────────────────────────────────────
    session_token = os.environ.get(SESSION_ENV, "").strip()
    if not session_token:
        print(f"[ERROR] '{SESSION_ENV}' env var is not set.")
        print(f"  Copy the value of {COOKIE_NAME} from top.gg DevTools → Application → Cookies.")
        sys.exit(1)

    if sync_playwright is None or PWTimeout is None:
        print("[ERROR] Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    max_retries = 3
    for attempt in range(1, max_retries + 2):
        if attempt > 1:
            print(f"\n[INFO] --- Starting Retry Attempt {attempt - 1}/{max_retries} ---")
            time.sleep(5)

        print(f"[INFO] Starting vote attempt {attempt} of {max_retries + 1}...")
        try:
            success, result_type = run_vote_attempt(session_token, attempt, max_retries)
            if success:
                sys.exit(0)
            
            if result_type == "CAPTCHA":
                if attempt <= max_retries:
                    print(f"[WARN] Captcha encountered on attempt {attempt}. Resetting browser and retrying...")
                    continue
                else:
                    print(f"[ERROR] Captcha encountered on attempt {attempt}. Max retries ({max_retries}) reached. Exiting.")
                    sys.exit(1)
            elif result_type == "LOGIN_FAILED":
                sys.exit(1)
            else:
                # For other errors (e.g. NO_VOTE_BUTTON, VOTE_FAILED), exit immediately
                sys.exit(1)

        except Exception as e:
            print(f"[ERROR] Attempt {attempt} failed with unexpected exception: {e}")
            if attempt <= max_retries:
                print("[INFO] Resetting browser and retrying...")
                continue
            else:
                sys.exit(1)


if __name__ == "__main__":
    main()
