#!/usr/bin/env python3
"""
Verify IG_USER_ID + IG_ACCESS_TOKEN are correct BEFORE trying to post.
Read-only -- publishes nothing.

Local:
    IG_USER_ID=... IG_ACCESS_TOKEN=... python3 scripts/verify_setup.py
In Actions: run the "Verify Instagram Setup" workflow.
"""
import os
import sys
import json
import time
import urllib.parse
import urllib.request
import urllib.error

V = os.getenv("GRAPH_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{V}"
UID = os.getenv("IG_USER_ID", "").strip()
TOK = os.getenv("IG_ACCESS_TOKEN", "").strip()

ok, warn, bad = [], [], []


def get(path, **params):
    params["access_token"] = TOK
    url = f"{GRAPH}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode()).get("error", {})
        except Exception:
            err = {"message": f"HTTP {e.code}"}
        return None, err


print("=" * 60)
print("INSTAGRAM SETUP VERIFICATION")
print("=" * 60)

# --- Secrets present at all? -------------------------------------------
if not UID:
    bad.append("IG_USER_ID is empty -- secret missing or misnamed")
if not TOK:
    bad.append("IG_ACCESS_TOKEN is empty -- secret missing or misnamed")
if bad:
    for b in bad:
        print(f"  [FAIL] {b}")
    print("\nAdd them under Settings > Secrets and variables > Actions.")
    sys.exit(1)

print(f"  [ OK ] IG_USER_ID present ({UID[:4]}...{UID[-3:]}, {len(UID)} chars)")
print(f"  [ OK ] IG_ACCESS_TOKEN present ({len(TOK)} chars)")
if not UID.isdigit():
    warn.append("IG_USER_ID is not all digits -- should be a numeric ID, "
                "not a username")
if len(TOK) < 100:
    warn.append(f"Token is only {len(TOK)} chars -- long-lived tokens are "
                "usually 150+. Did you skip the fb_exchange_token step?")

# --- Token validity + expiry -------------------------------------------
print("\n--- Token ---")
dbg, err = get("debug_token", input_token=TOK)
if err:
    print(f"  [FAIL] Token rejected: {err.get('message')}")
    sys.exit(1)
d = (dbg or {}).get("data", {})
if not d.get("is_valid"):
    print(f"  [FAIL] Token invalid: {d.get('error', {}).get('message', '?')}")
    sys.exit(1)
print(f"  [ OK ] Valid | app_id={d.get('app_id')} type={d.get('type')}")

exp = d.get("expires_at", 0)
if exp == 0:
    print("  [ OK ] Never expires")
else:
    days = (exp - time.time()) / 86400
    line = f"expires in {days:.0f} days ({time.strftime('%Y-%m-%d', time.localtime(exp))})"
    if days < 7:
        bad.append(f"Token {line} -- refresh it now")
        print(f"  [FAIL] {line}")
    elif days < 21:
        warn.append(f"Token {line}")
        print(f"  [WARN] {line}")
    else:
        print(f"  [ OK ] {line}")

scopes = d.get("scopes", [])
print(f"  Scopes: {', '.join(scopes) if scopes else '(none reported)'}")
need = "instagram_content_publish"
alt = "instagram_business_content_publish"
if need not in scopes and alt not in scopes:
    bad.append(f"Missing '{need}' scope -- cannot publish. Regenerate the "
               "token with that permission ticked.")
    print(f"  [FAIL] Missing {need}")
else:
    print(f"  [ OK ] Publish scope granted")

# --- Account identity + type -------------------------------------------
print("\n--- Account ---")
acct, err = get(UID, fields="id,username,name,account_type,"
                            "media_count,followers_count")
if err:
    msg = err.get("message", "")
    print(f"  [FAIL] Cannot read account {UID}: {msg}")
    if "nonexisting field" in msg.lower() or err.get("code") == 100:
        print("         -> IG_USER_ID is probably a Facebook Page ID, not the "
              "Instagram account ID.")
        print("         -> Run: curl \"https://graph.facebook.com/" + V +
              "/PAGE_ID?fields=instagram_business_account&access_token=TOKEN\"")
    sys.exit(1)

print(f"  [ OK ] @{acct.get('username')} ({acct.get('name', '')})")
print(f"         media={acct.get('media_count')} "
      f"followers={acct.get('followers_count')}")
atype = acct.get("account_type")
if atype:
    if atype == "BUSINESS":
        print(f"  [ OK ] account_type = BUSINESS")
    else:
        bad.append(f"account_type = {atype}. Content publishing requires "
                   "BUSINESS. Creator accounts are rejected by the API.")
        print(f"  [FAIL] account_type = {atype} (needs BUSINESS)")

# --- The actual publishing permission ----------------------------------
print("\n--- Publishing ---")
lim, err = get(f"{UID}/content_publishing_limit",
               fields="config,quota_usage")
if err:
    bad.append(f"content_publishing_limit failed: {err.get('message')} "
               "-- this is the exact permission publishing needs.")
    print(f"  [FAIL] {err.get('message')}")
else:
    u = (lim.get("data") or [{}])[0]
    total = u.get("config", {}).get("quota_total", 100)
    print(f"  [ OK ] Quota endpoint reachable -- "
          f"{u.get('quota_usage', 0)}/{total} posts used in last 24h")

# --- Summary ------------------------------------------------------------
print("\n" + "=" * 60)
for w in warn:
    print(f"  [WARN] {w}")
for b in bad:
    print(f"  [FAIL] {b}")
if bad:
    print("\nRESULT: NOT READY -- fix the FAIL items above.")
    sys.exit(1)
print("\nRESULT: READY. Secrets are valid and the account can publish.")
if warn:
    print("        (warnings above are non-blocking)")
