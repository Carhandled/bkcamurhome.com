#!/usr/bin/env python3
"""
get_refresh_token.py

One-time helper to mint a fresh ETSY_REFRESH_TOKEN for the hands-off sync
in .github/workflows/etsy-sync.yml.

You only need this when the refresh-token chain has broken - i.e. the sync
job fails with:

    {"error":"invalid_grant","error_description":"refresh_token is invalid"}

That happens if the workflow stops running long enough for the stored token
to lapse, since Etsy rotates the refresh token on every use and sync_etsy.py
writes the new one back into the ETSY_REFRESH_TOKEN secret each run. Break
the chain and the only fix is to re-authorize by hand, which is what this
script does.

RUN THIS ON YOUR OWN MACHINE, not in CI - it needs a browser you're signed
into Etsy with. Requires only the Python standard library.

    python3 scripts/get_refresh_token.py

It will:
  1. Build an Etsy authorization URL (OAuth 2.0 + PKCE) and print it.
  2. You open it, sign in, and click "Allow Access".
  3. Etsy redirects to the callback page in this repo
     (etsy-oauth-callback.html), which prints the `code` value.
  4. You paste that code back here.
  5. It exchanges the code for an access token + refresh token and prints
     the refresh token.

Then paste that refresh token into the repo secret ETSY_REFRESH_TOKEN at:
  https://github.com/Carhandled/bkcamurhome.com/settings/secrets/actions

IMPORTANT: the --redirect-uri below must match a URL registered under
"Edit callback URLs" in the Etsy app dashboard, character for character
(including https:// and any www.).
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"

DEFAULT_REDIRECT_URI = "https://www.bkcamurhome.com/etsy-oauth-callback.html"

# sync_etsy.py only reads listings and their images, so these are the only
# scopes worth granting. Keep them minimal.
SCOPES = "listings_r shops_r"


def b64url(raw):
    """Base64url-encode without padding, per RFC 7636."""
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_pkce_pair():
    verifier = b64url(secrets.token_bytes(64))
    challenge = b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def build_auth_url(client_id, redirect_uri, challenge, state):
    # quote_via=quote so the space between scopes encodes as %20, not "+" -
    # Etsy's authorize endpoint does not accept the "+" form.
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        quote_via=urllib.parse.quote,
    )
    return f"{AUTH_URL}?{query}"


def extract_code(raw, expected_state):
    """Accept either a bare code or the full callback URL pasted from the
    browser address bar, since both are natural things to copy."""
    if "?" not in raw and "&" not in raw:
        return raw

    query = urllib.parse.urlparse(raw).query or raw.lstrip("?")
    params = urllib.parse.parse_qs(query)

    if "error" in params:
        print(
            f"ERROR: Etsy returned an error instead of a code: "
            f"{params['error'][0]}",
            file=sys.stderr,
        )
        sys.exit(1)

    got_state = params.get("state", [None])[0]
    if got_state and got_state != expected_state:
        # Not fatal on its own, but it means this URL came from a different
        # authorization attempt, whose verifier we no longer hold.
        print(
            "ERROR: that callback URL is from a different authorization run "
            f"(state {got_state!r}, expected {expected_state!r}).\n"
            "Re-run this script and use the URL it prints.",
            file=sys.stderr,
        )
        sys.exit(1)

    return (params.get("code") or [""])[0].strip()


def exchange_code(client_id, redirect_uri, code, verifier):
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"\nERROR: Etsy rejected the code exchange ({exc.code}).", file=sys.stderr)
        print(f"Response: {detail}", file=sys.stderr)
        print(
            "\nCommon causes:\n"
            "  - the redirect URI here does not exactly match the one registered\n"
            "    under 'Edit callback URLs' in the Etsy app dashboard\n"
            "  - the code was already used (each one works exactly once)\n"
            "  - more than a few minutes passed before pasting the code\n"
            "Re-run this script to start over with a fresh code.",
            file=sys.stderr,
        )
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Mint a new Etsy refresh token for the sync workflow."
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("ETSY_API_KEY", ""),
        help="Etsy app keystring. Defaults to $ETSY_API_KEY.",
    )
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"Registered callback URL. Default: {DEFAULT_REDIRECT_URI}",
    )
    args = parser.parse_args()

    client_id = args.client_id.strip()
    if not client_id:
        client_id = input("Etsy app keystring (client id): ").strip()
    if not client_id:
        print("ERROR: a keystring is required.", file=sys.stderr)
        sys.exit(1)

    verifier, challenge = make_pkce_pair()
    state = secrets.token_urlsafe(16)
    url = build_auth_url(client_id, args.redirect_uri, challenge, state)

    print("\n" + "=" * 72)
    print("STEP 1 - open this URL in a browser signed in to the Etsy shop owner")
    print("=" * 72)
    print(f"\n{url}\n")
    print("=" * 72)
    print("STEP 2 - click 'Allow Access'. Etsy redirects to the callback page,")
    print("         which shows a 'code' value. Copy it.")
    print(f"         (expected state: {state})")
    print("=" * 72)

    raw = input("\nPaste the code (or the whole callback URL) here: ").strip()
    code = extract_code(raw, state)
    if not code:
        print("ERROR: no authorization code found in that input.", file=sys.stderr)
        sys.exit(1)

    print("\nExchanging code for tokens...")
    data = exchange_code(client_id, args.redirect_uri, code, verifier)

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        print(f"ERROR: no refresh_token in response: {data}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 72)
    print("SUCCESS - new refresh token")
    print("=" * 72)
    print(f"\n{refresh_token}\n")
    print("=" * 72)
    print("STEP 3 - save it as the ETSY_REFRESH_TOKEN repo secret:")
    print("  https://github.com/Carhandled/bkcamurhome.com/settings/secrets/actions")
    print("\nThen run the 'Sync Etsy Listings' workflow to confirm it works.")
    print("From then on sync_etsy.py rotates the token itself on every run,")
    print("so you should not need this script again unless the sync stays")
    print("broken long enough for the chain to lapse.")
    print("=" * 72)


if __name__ == "__main__":
    main()
