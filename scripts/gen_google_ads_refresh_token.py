#!/usr/bin/env python3
"""Generate a Google Ads API OAuth refresh token (one-time, local).

Reads client_id/client_secret from env, opens a Google consent screen in your
browser, and prints the refresh token to THIS terminal. Nothing is written to
disk and no secret leaves your machine — copy the printed token into .env as
GOOGLE_ADS_REFRESH_TOKEN yourself.

Usage:
    export GOOGLE_ADS_CLIENT_ID=...        # from GCP OAuth client (Desktop app)
    export GOOGLE_ADS_CLIENT_SECRET=...
    python3 scripts/gen_google_ads_refresh_token.py

Prereqs: OAuth client of type "Desktop app" created in GCP, and the
"Google Ads API" enabled in the same project. Run inside the pipeline-api venv
(has google-auth-oauthlib): pipeline-api/.venv/bin/python scripts/gen_google_ads_refresh_token.py
"""
import os
import sys

# Full Google Ads API access scope — required for KeywordPlanIdeaService.
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> int:
    client_id = os.getenv("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_ADS_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "ERROR: set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET first "
            "(from your GCP OAuth 'Desktop app' client).",
            file=sys.stderr,
        )
        return 1

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "ERROR: google-auth-oauthlib missing. Run with the pipeline-api venv:\n"
            "  pipeline-api/.venv/bin/python scripts/gen_google_ads_refresh_token.py",
            file=sys.stderr,
        )
        return 1

    # Desktop-app client config built from env — no client_secrets.json on disk.
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # Opens a local browser; you approve, token comes back to a localhost port.
    # access_type=offline + prompt=consent guarantees a refresh_token is returned.
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )

    if not creds.refresh_token:
        print(
            "ERROR: no refresh_token returned. Revoke prior access at "
            "https://myaccount.google.com/permissions and retry.",
            file=sys.stderr,
        )
        return 1

    print("\n" + "=" * 60)
    print("Copy this into .env as GOOGLE_ADS_REFRESH_TOKEN:")
    print("=" * 60)
    print(creds.refresh_token)
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
