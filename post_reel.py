#!/usr/bin/env python3
"""
Publish a Reel to Instagram from a public URL (e.g. your GitHub CDN repo).

Flow (Instagram Content Publishing API):
  1. POST /{ig-user-id}/media           -> create container (async video fetch)
  2. GET  /{container-id}?fields=status_code -> poll until FINISHED
  3. POST /{ig-user-id}/media_publish   -> go live

Env vars required:
  IG_USER_ID       Instagram *Business* account ID (numeric)
  IG_ACCESS_TOKEN  Long-lived token w/ instagram_business_content_publish
  VIDEO_URL        Public HTTPS mp4 URL
Optional:
  COVER_URL, CAPTION, SHARE_TO_FEED (true/false), GRAPH_VERSION
"""

import os
import sys
import time
import json
import urllib.parse
import urllib.request
import urllib.error

GRAPH = f"https://graph.facebook.com/{os.getenv('GRAPH_VERSION', 'v21.0')}"

IG_USER_ID = os.environ["IG_USER_ID"]
TOKEN = os.environ["IG_ACCESS_TOKEN"]
VIDEO_URL = os.environ["VIDEO_URL"]
COVER_URL = os.getenv("COVER_URL", "").strip()
CAPTION = os.getenv("CAPTION", "").strip()
SHARE_TO_FEED = os.getenv("SHARE_TO_FEED", "true").strip().lower()

POLL_INTERVAL = 10          # seconds between status checks
POLL_TIMEOUT = 15 * 60      # give Meta 15 min to ingest the video


def call(method, path, params):
    url = f"{GRAPH}/{path}"
    params = {**params, "access_token": TOKEN}
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        url = f"{url}?{data.decode()}"
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        # Never echo the token into CI logs
        print(f"::error::Graph API {e.code}: {body}", file=sys.stderr)
        raise SystemExit(1)


def preflight():
    """Fail fast if the URL isn't publicly reachable — Meta must fetch it."""
    req = urllib.request.Request(VIDEO_URL, method="HEAD",
                                 headers={"User-Agent": "ig-autopost/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            size = int(r.headers.get("Content-Length") or 0)
            ctype = r.headers.get("Content-Type", "?")
            print(f"Video reachable: {r.status} | {ctype} | {size/1e6:.1f} MB")
            if size > 100 * 1024 * 1024:
                print("::warning::Video >100MB — Meta may reject it.")
    except Exception as e:
        raise SystemExit(f"Video URL not publicly reachable: {e}")


def quota():
    q = call("GET", f"{IG_USER_ID}/content_publishing_limit",
             {"fields": "config,quota_usage"})
    usage = q.get("data", [{}])[0]
    print(f"Publishing quota: {usage.get('quota_usage')} / "
          f"{usage.get('config', {}).get('quota_total', 100)} in last 24h")


def create_container():
    params = {
        "media_type": "REELS",
        "video_url": VIDEO_URL,
        "share_to_feed": SHARE_TO_FEED,
    }
    if CAPTION:
        params["caption"] = CAPTION
    if COVER_URL:
        params["cover_url"] = COVER_URL
    res = call("POST", f"{IG_USER_ID}/media", params)
    print(f"Container created: {res['id']}")
    return res["id"]


def wait_ready(container_id):
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        res = call("GET", container_id, {"fields": "status_code,status"})
        code = res.get("status_code")
        print(f"  status={code}")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise SystemExit(f"Container failed: {res.get('status')}")
        time.sleep(POLL_INTERVAL)
    raise SystemExit("Timed out waiting for video processing.")


def publish(container_id):
    res = call("POST", f"{IG_USER_ID}/media_publish",
               {"creation_id": container_id})
    media_id = res["id"]
    link = call("GET", media_id, {"fields": "permalink"}).get("permalink", "")
    print(f"::notice::Published! media_id={media_id} {link}")
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### Reel published \n\n- Media ID: `{media_id}`\n"
                    f"- Link: {link}\n- Source: {VIDEO_URL}\n")


if __name__ == "__main__":
    preflight()
    quota()
    cid = create_container()
    wait_ready(cid)
    publish(cid)
