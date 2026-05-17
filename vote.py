#!/usr/bin/env python3
"""
Karuta Top.gg Auto-Voter
Votes for Karuta bot on top.gg using the GraphQL API with cookie-based auth.

Required environment variables:
  TOPGG_SESSION_TOKEN  - Value of the __Secure-next-auth.session-token cookie from top.gg
"""

import os
import sys
import json
import uuid
import base64
import requests

# ── Config ────────────────────────────────────────────────────────────────────
GRAPHQL_URL = "https://api.top.gg/graphql"
ENTITY_ID   = "4283790394010009600"   # Karuta's internal top.gg entity ID
BOT_ID      = "646937666251915264"    # Karuta's Discord app/bot ID
COOKIE_NAME  = "__Secure-authjs.session-token"   # Auth.js v5 cookie name used by top.gg
SESSION_ENV  = "TOPGG_SESSION_TOKEN"

VOTE_MUTATION = """
mutation VoteEntity($entityId: String!, $encodedData: String!, $query: String!) {
  voteEntity(entityId: $entityId, encodedData: $encodedData, query: $query) {
    isAcknowledged
    newVoteCount
    canRetry
    error
    captchaProvider
  }
}
""".strip()

CHECK_QUERY = """
query gvs($i: String!) {
  entity(id: $i) {
    id
    voteStatus {
      timeUntilNextVote
      status
      id
      isSubscribed
    }
  }
}
""".strip()

HEADERS = {
    "accept": "application/json",
    "accept-language": "en",
    "content-type": "application/json",
    "origin": "https://top.gg",
    "referer": "https://top.gg/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Chromium";v="148", "Brave";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


def make_encoded_data() -> str:
    """Generate the trace ID payload (base64-encoded JSON) required by the mutation."""
    trace_id = str(uuid.uuid4())
    payload = json.dumps({"traceId": trace_id})
    return base64.b64encode(payload.encode()).decode()


def build_cookie_header(session_token: str) -> str:
    """
    Build the Cookie header string.
    top.gg uses Auth.js v5 — the session cookie is __Secure-authjs.session-token.
    It's same-site with api.top.gg so the browser sends it automatically;
    we replicate that by including it explicitly in the Cookie header.
    """
    return f"{COOKIE_NAME}={session_token}"


def check_vote_status(session: requests.Session) -> dict:
    """Check current vote status for the entity."""
    payload = {
        "query": CHECK_QUERY,
        "operationName": "gvs",
        "variables": {"i": ENTITY_ID},
    }
    resp = session.post(GRAPHQL_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    entity = (data.get("data") or {}).get("entity") or {}
    return entity.get("voteStatus") or {}


def cast_vote(session: requests.Session) -> dict:
    """Submit the vote mutation."""
    payload = {
        "query": VOTE_MUTATION,
        "operationName": "VoteEntity",
        "variables": {
            "entityId": ENTITY_ID,
            "encodedData": make_encoded_data(),
            "query": "",
        },
    }
    resp = session.post(GRAPHQL_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data["data"]["voteEntity"]


def main() -> None:
    # ── Read session token ─────────────────────────────────────────────────
    session_token = os.environ.get(SESSION_ENV, "").strip()
    if not session_token:
        print(f"[ERROR] Environment variable '{SESSION_ENV}' is not set or empty.")
        print(f"Set it to the value of the {COOKIE_NAME} cookie from top.gg.")
        sys.exit(1)

    # ── Set up session ─────────────────────────────────────────────────────
    session = requests.Session()
    session.headers.update(HEADERS)
    session.headers["cookie"] = build_cookie_header(session_token)

    print(f"[INFO] Checking vote status for Karuta (entity: {ENTITY_ID}) ...")
    try:
        status = check_vote_status(session)
        print(f"[INFO] Vote status: {status}")

        vote_state = status.get("status", "UNKNOWN")
        time_until_next = status.get("timeUntilNextVote", 0)

        if vote_state == "VOTED":
            hours = time_until_next / 3600 if time_until_next else 0
            print(f"[INFO] Already voted. Next vote available in {hours:.1f} hours.")
            print("[SKIP] No vote cast – exiting cleanly.")
            sys.exit(0)

    except Exception as e:
        print(f"[WARN] Could not fetch vote status: {e}. Proceeding to vote anyway ...")

    # ── Cast vote ──────────────────────────────────────────────────────────
    print("[INFO] Casting vote ...")
    try:
        result = cast_vote(session)
    except requests.HTTPError as e:
        print(f"[ERROR] HTTP error while voting: {e}")
        print(f"        Response body: {e.response.text[:500]}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error while voting: {e}")
        sys.exit(1)

    # ── Interpret result ───────────────────────────────────────────────────
    acknowledged = result.get("isAcknowledged", False)
    new_count     = result.get("newVoteCount", "?")
    can_retry     = result.get("canRetry", False)
    error         = result.get("error", "NONE")
    captcha       = result.get("captchaProvider")

    if error and error != "NONE":
        print(f"[ERROR] Vote failed with error: {error}")
        if captcha:
            print(f"        Captcha required from provider: {captcha}")
            print("        ⚠ The session cookie may be stale or the IP is being flagged.")
        sys.exit(1)

    if acknowledged:
        print(f"[SUCCESS] ✅ Vote cast! Total votes for Karuta: {new_count}")
        if can_retry:
            print("[INFO]   canRetry=true – weekend double-vote may apply.")
    else:
        print(f"[WARN] Vote not acknowledged. Full result: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()
