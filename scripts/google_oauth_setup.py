#!/usr/bin/env python3
"""
Google OAuth Setup — One-time script to get refresh tokens.

Usage:
    1. Create a Google Cloud project
    2. Enable Calendar API and Gmail API
    3. Create OAuth 2.0 credentials (Desktop app)
    4. Download the client secret JSON or set env vars:
       GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET
    5. Run: python scripts/google_oauth_setup.py
    6. Follow the URL in the browser, paste the authorization code
    7. Tokens are saved to secrets/google_tokens.json
"""

import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Install requests first: pip install requests")
    sys.exit(1)

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

TOKEN_OUTPUT = os.getenv("GOOGLE_TOKEN_OUTPUT", "secrets/google_tokens.json")


def main():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables.")
        print("You can get these from Google Cloud Console → APIs & Services → Credentials.")
        sys.exit(1)

    scope_str = " ".join(SCOPES)
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        "response_type=code&"
        f"scope={scope_str}&"
        "access_type=offline&"
        "prompt=consent&"
        "redirect_uri=urn:ietf:wg:oauth:2.0:oob"
    )

    print("\n=== Google OAuth Setup ===\n")
    print("1. Open this URL in your browser:\n")
    print(f"   {auth_url}\n")
    print("2. Sign in and grant access")
    print("3. Copy the authorization code and paste it below\n")

    code = input("Authorization code: ").strip()
    if not code:
        print("No code entered. Aborting.")
        sys.exit(1)

    # Exchange code for tokens
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        },
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"Error exchanging code: {resp.status_code} {resp.text}")
        sys.exit(1)

    data = resp.json()
    tokens = {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": time.time() + data.get("expires_in", 3600),
        "scopes": SCOPES,
    }

    os.makedirs(os.path.dirname(TOKEN_OUTPUT), exist_ok=True)
    with open(TOKEN_OUTPUT, "w") as f:
        json.dump(tokens, f, indent=2)

    print(f"\nTokens saved to {TOKEN_OUTPUT}")
    print("You can now start the Calendar and Gmail agents.")


if __name__ == "__main__":
    main()
