#!/usr/bin/env python3
"""
Upload the same reel to YouTube as a Short.

Key difference from Instagram: YouTube does NOT fetch from a URL. You must
upload the bytes. This does a resumable upload so a dropped connection
retries instead of restarting.

Auth is OAuth2 with a refresh token (never expires unless revoked, or 7 days
if the app is stuck in "Testing" -- publish it to Production).

Env vars required:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
  VIDEO_URL         public mp4 to download and re-upload
Optional:
  CAPTION_FILE      reuses posts/caption.txt (default)
  YT_TITLE          else derived from the caption's first line
  YT_PRIVACY        public | unlisted | private   (default public)
  YT_CATEGORY_ID    default 25 (News & Politics)
  YT_MADE_FOR_KIDS  true | false                  (default false)
"""

import os
import re
import sys
import json
import time
import urllib.parse
import urllib.request
import urllib.error

CLIENT_ID = os.environ["YT_CLIENT_ID"]
CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]
VIDEO_URL = os.environ["VIDEO_URL"]

CAPTION_FILE = os.getenv("CAPTION_FILE", "posts/caption.txt").strip()
PRIVACY = os.getenv("YT_PRIVACY", "public").strip().lower()
CATEGORY_ID = os.getenv("YT_CATEGORY_ID", "25").strip()
MADE_FOR_KIDS = os.getenv("YT_MADE_FOR_KIDS", "false").strip().lower() == "true"

TITLE_MAX = 100        # YouTube hard limit
DESC_MAX = 5000        # YouTube hard limit
TAG_MAX = 15           # keep well under the 500-char total tag budget
CHUNK = 5 * 1024 * 1024


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- auth
def access_token():
    """Exchange the long-lived refresh token for a 1-hour access token."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token",
                                 data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"::error::OAuth refresh failed ({e.code}): {body}",
              file=sys.stderr)
        if "invalid_grant" in body:
            print("\n  invalid_grant almost always means one of:", file=sys.stderr)
            print("   - The OAuth app is still in 'Testing' mode, so refresh",
                  file=sys.stderr)
            print("     tokens expire after 7 days. Publish it to Production.",
                  file=sys.stderr)
            print("   - The token was revoked, or the client secret changed.",
                  file=sys.stderr)
            print("   - Re-run scripts/get_youtube_token.py to mint a new one.",
                  file=sys.stderr)
        raise SystemExit(1)


# ------------------------------------------------------------- metadata
def build_metadata():
    """Derive title/description/tags from the same caption.txt Instagram uses."""
    caption = ""
    if CAPTION_FILE and os.path.exists(CAPTION_FILE):
        with open(CAPTION_FILE, encoding="utf-8") as f:
            caption = f.read().strip()
        log(f"Caption: {len(caption)} chars from {CAPTION_FILE}")
    else:
        log(f"::warning::{CAPTION_FILE} not found -- using generic metadata")

    # Tags from hashtags, minus the '#'
    tags = []
    for t in re.findall(r"#(\w+)", caption):
        if t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    tags = tags[:TAG_MAX]

    title = os.getenv("YT_TITLE", "").strip()
    if not title:
        # First non-empty line of the caption, stripped of hashtags/emoji noise
        first = next((l.strip() for l in caption.splitlines() if l.strip()),
                     "Daily News Brief")
        first = re.sub(r"#\w+", "", first).strip(" -|—•").strip()
        title = first or "Daily News Brief"

    # YouTube rejects < and > in titles outright.
    title = title.replace("<", "").replace(">", "")
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1].rsplit(" ", 1)[0] + "…"
        log(f"::warning::Title trimmed to {len(title)} chars")

    # #Shorts in the description is the documented hint for Shorts placement.
    desc = caption or title
    if "#shorts" not in desc.lower():
        desc = f"{desc}\n\n#Shorts"
    if len(desc) > DESC_MAX:
        desc = desc[:DESC_MAX - 1].rsplit(" ", 1)[0] + "…"
        log(f"::warning::Description trimmed to {len(desc)} chars")

    log(f"Title      : {title}")
    log(f"Tags       : {', '.join(tags) if tags else '(none)'}")
    log(f"Privacy    : {PRIVACY}")
    return {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags,
            "categoryId": CATEGORY_ID,
        },
        "status": {
            "privacyStatus": PRIVACY,
            "selfDeclaredMadeForKids": MADE_FOR_KIDS,
        },
    }


# --------------------------------------------------------------- video
def fetch_video():
    log(f"Downloading {VIDEO_URL}")
    req = urllib.request.Request(
        VIDEO_URL, headers={"User-Agent": "Mozilla/5.0 (compatible; YTBot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
            ctype = r.headers.get("Content-Type", "?")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Could not download video: HTTP {e.code}")
    log(f"  {len(data)/1e6:.2f} MB, {ctype}")
    if len(data) < 1000:
        raise SystemExit("Downloaded file is suspiciously small -- aborting.")
    return data


# -------------------------------------------------------------- upload
def start_session(token, meta, size):
    body = json.dumps(meta).encode("utf-8")
    url = ("https://www.googleapis.com/upload/youtube/v3/videos"
           "?uploadType=resumable&part=snippet,status")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(size),
        "X-Upload-Content-Type": "video/mp4",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            loc = r.headers.get("Location")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"::error::Could not start upload ({e.code}): {body}",
              file=sys.stderr)
        if "quotaExceeded" in body:
            print("\n  Daily quota gone. An upload costs 1600 of the 10,000",
                  file=sys.stderr)
            print("  free units, so ~6 uploads/day. Resets midnight Pacific.",
                  file=sys.stderr)
        elif "youtubeSignupRequired" in body:
            print("\n  That Google account has no YouTube channel yet.",
                  file=sys.stderr)
        raise SystemExit(1)
    if not loc:
        raise SystemExit("No resumable session URL returned.")
    return loc


def upload(session_url, data):
    """Send the file in chunks, retrying transient failures with backoff."""
    size = len(data)
    sent = 0
    attempt = 0
    while sent < size:
        end = min(sent + CHUNK, size) - 1
        chunk = data[sent:end + 1]
        req = urllib.request.Request(session_url, data=chunk, method="PUT",
                                     headers={
            "Content-Length": str(len(chunk)),
            "Content-Range": f"bytes {sent}-{end}/{size}",
        })
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                pct = 100.0
                log(f"  {pct:5.1f}%  upload complete")
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 308:                       # incomplete: continue
                rng = e.headers.get("Range")
                sent = int(rng.split("-")[1]) + 1 if rng else end + 1
                attempt = 0
                log(f"  {sent/size*100:5.1f}%  ({sent/1e6:.1f} MB)")
                continue
            if e.code in (500, 502, 503, 504) and attempt < 5:
                attempt += 1
                wait = 2 ** attempt
                log(f"  transient {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            print(f"::error::Upload failed ({e.code}): {e.read().decode()}",
                  file=sys.stderr)
            raise SystemExit(1)
        except Exception as e:
            if attempt < 5:
                attempt += 1
                wait = 2 ** attempt
                log(f"  {type(e).__name__}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise SystemExit(f"Upload failed: {e}")
    raise SystemExit("Upload ended without a response body.")


def main():
    meta = build_metadata()
    data = fetch_video()
    token = access_token()
    log("Starting resumable upload...")
    session = start_session(token, meta, len(data))
    res = upload(session, data)

    vid = res.get("id")
    status = (res.get("status") or {})
    actual = status.get("privacyStatus")
    link = f"https://youtu.be/{vid}"
    log(f"\n::notice::Uploaded! {link}")
    log(f"  video id       : {vid}")
    log(f"  privacy status : {actual}")

    if actual == "private" and PRIVACY != "private":
        log("\n::warning::YouTube forced this video to PRIVATE.")
        log("  Uploads from API projects created after 28 July 2020 are")
        log("  locked private until the project passes YouTube's compliance")
        log("  audit. Apply here, then re-upload:")
        log("  https://support.google.com/youtube/contact/yt_api_form")

    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### YouTube\n\n- {link}\n- privacy: `{actual}`\n"
                    f"- title: {meta['snippet']['title']}\n")


if __name__ == "__main__":
    main()
