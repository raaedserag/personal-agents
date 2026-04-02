"""
Google OAuth — Token management for Calendar and Gmail agents.

Handles token refresh using a stored refresh_token.
Run scripts/google_oauth_setup.py once to get the initial tokens.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

# Token file location — mounted via Docker volume or local secrets
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "/app/data/google_tokens.json")


def _load_tokens() -> dict:
    """Load stored tokens from disk."""
    path = Path(TOKEN_FILE)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_tokens(tokens: dict) -> None:
    """Persist tokens to disk."""
    path = Path(TOKEN_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(tokens, f)


def get_access_token() -> str | None:
    """Get a valid access token, refreshing if needed.

    Requires GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET env vars
    and a stored refresh_token in the token file.
    """
    tokens = _load_tokens()
    if not tokens.get("refresh_token"):
        return None

    # Check if current token is still valid (with 60s buffer)
    if tokens.get("access_token") and tokens.get("expires_at", 0) > time.time() + 60:
        return tokens["access_token"]

    # Refresh the token
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": tokens["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=10,
    )

    if resp.status_code != 200:
        return None

    data = resp.json()
    tokens["access_token"] = data["access_token"]
    tokens["expires_at"] = time.time() + data.get("expires_in", 3600)
    _save_tokens(tokens)

    return tokens["access_token"]


def google_request(method: str, url: str, **kwargs) -> dict:
    """Make an authenticated Google API request."""
    token = get_access_token()
    if not token:
        return {"error": "Google OAuth not configured. Run scripts/google_oauth_setup.py first."}

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    kwargs["headers"] = headers
    kwargs.setdefault("timeout", 15)

    try:
        resp = requests.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.text else {}
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        body = e.response.text[:300] if e.response else ""
        return {"error": f"Google API HTTP {status}: {body}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to Google API"}
    except requests.exceptions.Timeout:
        return {"error": "Google API request timed out"}
