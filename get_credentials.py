#!/usr/bin/env python3
"""
Get your IG_USER_ID and long-lived IG_ACCESS_TOKEN in one step.

You supply three things from the Meta dashboard:
  - App ID           (Settings > Basic)
  - App Secret       (Settings > Basic > Show)
  - Short-lived token (Graph API Explorer > Generate Access Token)

This does the rest:
  1. Exchanges the 1-hour token for a 60-day one
  2. Lists your Facebook Pages
  3. Finds the Instagram Business account attached to each
  4. Prints the exact two values to paste into GitHub secrets

Run:
    python3 scripts/get_credentials.py
    python3 scripts/get_credentials.py --app-id X --app-secret Y --token Z
"""
import sys
import json
import time
import argparse
import getpass
import urllib.parse
import urllib.request
import urllib.error

V = "v21.0"
GRAPH = f"https://graph.facebook.com/{V}"


def get(path, **params):
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode()).get("error", {})
        except Exception:
            err = {"message": f"HTTP {e.code}"}
        print(f"\n  ERROR: {err.get('message')}")
        if err.get("code") == 190:
            print("  -> Token is invalid or already expired.")
            print("     Short-lived tokens die after ~1 hour. Generate a "
                  "fresh one in Graph API Explorer and re-run.")
        elif err.get("code") == 100:
            print("  -> Check the App ID / App Secret are correct.")
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-id")
    ap.add_argument("--app-secret")
    ap.add_argument("--token", help="short-lived token from Graph Explorer")
    a = ap.parse_args()

    print("=" * 64)
    print("INSTAGRAM CREDENTIALS HELPER")
    print("=" * 64)
    print("\nFrom https://developers.facebook.com/apps -> your app:")

    app_id = a.app_id or input("  App ID              : ").strip()
    app_secret = a.app_secret or getpass.getpass(
        "  App Secret (hidden) : ").strip()
    short = a.token or getpass.getpass(
        "  Short-lived token   : ").strip()

    if not (app_id and app_secret and short):
        sys.exit("\nAll three values are required.")

    # ---- 1. Upgrade the token -----------------------------------------
    print("\n[1/3] Exchanging for a long-lived (60-day) token...")
    res = get("oauth/access_token",
              grant_type="fb_exchange_token",
              client_id=app_id,
              client_secret=app_secret,
              fb_exchange_token=short)
    long_tok = res["access_token"]
    secs = res.get("expires_in", 0)
    print(f"      Got it. Valid ~{secs // 86400 if secs else 60} days. "
          f"({len(long_tok)} chars)")

    # ---- 2. Sanity-check scopes ---------------------------------------
    dbg = get("debug_token", input_token=long_tok,
              access_token=long_tok).get("data", {})
    scopes = dbg.get("scopes", [])
    print(f"      Scopes: {', '.join(scopes) or '(none)'}")
    if not any(s in scopes for s in
               ("instagram_content_publish",
                "instagram_business_content_publish")):
        print("\n      WARNING: 'instagram_content_publish' is NOT granted.")
        print("      Publishing will fail. In Graph API Explorer, tick that")
        print("      permission, regenerate, and run this again.")

    # ---- 3. Find the Instagram account --------------------------------
    print("\n[2/3] Listing your Facebook Pages...")
    pages = get("me/accounts", access_token=long_tok,
                fields="id,name").get("data", [])
    if not pages:
        print("      No Pages found.")
        print("      -> Instagram publishing requires a Facebook Page linked")
        print("         to the Instagram account. Create one, link it, then")
        print("         regenerate the token (new Pages need re-consent).")
        sys.exit(1)
    for p in pages:
        print(f"      - {p['name']} (Page ID {p['id']})")

    print("\n[3/3] Looking for linked Instagram Business accounts...")
    found = []
    for p in pages:
        r = get(p["id"], fields="instagram_business_account{id,username,"
                                "account_type,media_count,followers_count}",
                access_token=long_tok)
        iga = r.get("instagram_business_account")
        if iga:
            found.append((p, iga))
            print(f"      FOUND: @{iga.get('username')} "
                  f"(ID {iga['id']}) via Page '{p['name']}'")
            print(f"             type={iga.get('account_type')} "
                  f"media={iga.get('media_count')} "
                  f"followers={iga.get('followers_count')}")
        else:
            print(f"      none on Page '{p['name']}'")

    if not found:
        print("\n  No Instagram Business account is linked to any Page.")
        print("  Fix, in order:")
        print("    1. Instagram app > Settings > Account type > Business")
        print("       (Creator will NOT work)")
        print("    2. Link that account to a Facebook Page")
        print("    3. Regenerate the short-lived token and re-run this")
        sys.exit(1)

    if len(found) > 1:
        print("\n  Multiple accounts found -- pick the one you want to post "
              "to.")

    page, iga = found[0]
    uid = iga["id"]

    if iga.get("account_type") and iga["account_type"] != "BUSINESS":
        print(f"\n  WARNING: account_type is {iga['account_type']}, not "
              "BUSINESS.")
        print("  The publishing API rejects Creator accounts.")

    # ---- Output --------------------------------------------------------
    exp = time.strftime('%Y-%m-%d',
                        time.localtime(time.time() + (secs or 60 * 86400)))
    print("\n" + "=" * 64)
    print("PASTE THESE INTO GITHUB SECRETS")
    print("Settings > Secrets and variables > Actions > New repository secret")
    print("=" * 64)
    print(f"\n  Name : IG_USER_ID")
    print(f"  Value: {uid}")
    print(f"\n  Name : IG_ACCESS_TOKEN")
    print(f"  Value: {long_tok}")
    print(f"\n  (token expires around {exp})")
    print("\nOptional, for the monthly auto-refresh workflow:")
    print(f"  META_APP_ID     = {app_id}")
    print(f"  META_APP_SECRET = (the secret you just entered)")

    with open("credentials.txt", "w") as f:
        f.write(f"IG_USER_ID={uid}\nIG_ACCESS_TOKEN={long_tok}\n"
                f"META_APP_ID={app_id}\n# expires ~{exp}\n")
    print("\nAlso written to credentials.txt")
    print("DELETE that file once the secrets are saved -- never commit it.")


if __name__ == "__main__":
    main()
