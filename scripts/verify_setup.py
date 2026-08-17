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

_dae = d.get("data_access_expires_at", 0)
if _dae:
    ddays = (_dae - time.time()) / 86400
    dline = (f"Data access expires in {ddays:.0f} days "
             f"({time.strftime('%Y-%m-%d', time.localtime(_dae))})")
    # This is separate from token expiry: even a 'never expires' token
    # STOPS returning data once data-access lapses (~90 days).
    if ddays < 7:
        bad.append(f"{dline} -- re-authorise now")
        print(f"  [FAIL] {dline}")
    elif ddays < 21:
        warn.append(dline)
        print(f"  [WARN] {dline}")
    else:
        print(f"  [ OK ] {dline}")

exp = d.get("expires_at", 0)
if exp == 0:
    print("  [ OK ] Token expiry: Never "
          "(still bounded by data access above)")
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

# --- Account identity ---------------------------------------------------
# NOTE: 'account_type' does NOT exist on the IG User node of the Graph API
# (it is a Basic Display API field). Requesting it makes Meta reject the
# whole query with code 100. Business-vs-Creator is instead proven by the
# content_publishing_limit call below, which only Business accounts can use.
print("\n--- Account ---")
FIELD_SETS = [
    "id,username,name,media_count,followers_count",
    "id,username,media_count",
    "id,username",
    "id",
]
acct, err = None, None
for fs in FIELD_SETS:
    acct, err = get(UID, fields=fs)
    if not err:
        break
    if "nonexisting field" not in err.get("message", "").lower():
        break   # a real problem (bad id / permissions), not a field issue

if err:
    msg = err.get("message", "")
    print(f"  [FAIL] Cannot read account {UID}: {msg}")
    low = msg.lower()
    if "nonexisting field" in low and "node type (user)" not in low:
        print("         -> Unsupported field for this node (script bug, "
              "not your setup).")
    elif err.get("code") in (100, 803) or "unsupported get request" in low:
        print("         -> IG_USER_ID may be a Facebook Page ID rather than "
              "the Instagram account ID.")
        print("         -> Run: curl \"https://graph.facebook.com/" + V +
              "/PAGE_ID?fields=instagram_business_account&access_token=TOKEN\"")
    elif err.get("code") == 190:
        print("         -> Token problem, not an ID problem.")
    sys.exit(1)

uname = acct.get("username")
print(f"  [ OK ] Account {UID} readable"
      + (f" -- @{uname}" if uname else ""))
if acct.get("name"):
    print(f"         name={acct['name']}")
_stats = [f"{k}={acct[k]}" for k in ("media_count", "followers_count")
          if acct.get(k) is not None]
if _stats:
    print("         " + "  ".join(_stats))

# --- The actual publishing permission ----------------------------------
print("\n--- Publishing ---")
lim, err = get(f"{UID}/content_publishing_limit",
               fields="config,quota_usage")
if err:
    msg = err.get("message", "")
    bad.append(f"content_publishing_limit failed: {msg}")
    print(f"  [FAIL] {msg}")
    print("         This endpoint is the real test -- it only works for")
    print("         Instagram BUSINESS accounts with publish permission.")
    print("         If the token and ID both check out above, the account")
    print("         is likely still Creator, or needs App Review /")
    print("         your user added under App roles while in dev mode.")
else:
    u = (lim.get("data") or [{}])[0]
    total = u.get("config", {}).get("quota_total", 100)
    used = u.get("quota_usage", 0)
    print(f"  [ OK ] Quota endpoint reachable -- "
          f"{used}/{total} posts used in last 24h")
    print("  [ OK ] Account is BUSINESS with publishing rights")
    print("         (this endpoint rejects Personal/Creator accounts)")
    if used >= total:
        bad.append(f"Daily publish quota exhausted ({used}/{total}).")

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
