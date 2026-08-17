#!/usr/bin/env python3
"""
Pick a public video URL that Meta can actually fetch.

Tries several hosts in order and returns the first that passes ALL of:
  - HTTP 200
  - Content-Type is video/* (Meta rejects application/octet-stream)
  - Accept-Ranges: bytes  AND a real 206 on a range request
    (Meta's fetcher uses range requests; hosts that ignore them fail)

Why not just jsDelivr: it does not reliably serve every repo/commit and
returns "Failed to fetch the requested commit" 404s. GitHub Pages serves
the same bytes with a correct video/mp4 content-type and range support.

Usage:
    python3 scripts/resolve_url.py posts/reel.mp4 OWNER REPO [SHA]
Writes video_url=... to $GITHUB_OUTPUT when running in Actions.
"""
import os
import sys
import urllib.request
import urllib.error


def probe(url):
    """Return (ok, detail) after checking status, type and range support."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; IGBot/1.0)",
                          "Range": "bytes=0-1023"})
        with urllib.request.urlopen(req, timeout=45) as r:
            status = r.status
            ctype = (r.headers.get("Content-Type") or "").lower()
            ranges = (r.headers.get("Accept-Ranges") or "").lower()
            body = len(r.read())
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

    if status not in (200, 206):
        return False, f"HTTP {status}"
    if not ctype.startswith("video/"):
        return False, f"content-type {ctype or '?'} (need video/*)"
    if status != 206 and "bytes" not in ranges:
        return False, "no range support"
    return True, f"HTTP {status} {ctype} range-ok ({body}B probe)"


def candidates(owner, repo, path, sha):
    """Ordered best-first. Commit-pinned variants come first when available."""
    pages_host = f"{owner.lower()}.github.io"
    out = []
    # GitHub Pages: correct video/mp4 + range support. Not commit-pinned,
    # so we add a cache-busting query so Meta never reuses an old fetch.
    base = f"https://{pages_host}/{repo}/{path}"
    if sha:
        out.append((f"{base}?v={sha[:12]}", "GitHub Pages (cache-busted)"))
    out.append((base, "GitHub Pages"))
    # jsDelivr: great when it works, unreliable per-commit. Try after Pages.
    if sha:
        out.append((f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@{sha}/{path}",
                    "jsDelivr @sha"))
    out.append((f"https://cdn.jsdelivr.net/gh/{owner}/{repo}@main/{path}",
                "jsDelivr @main"))
    # Statically mirrors raw with a proper content-type.
    out.append((f"https://cdn.statically.io/gh/{owner}/{repo}/main/{path}",
                "Statically"))
    return out


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    path, owner, repo = sys.argv[1], sys.argv[2], sys.argv[3]
    sha = sys.argv[4] if len(sys.argv) > 4 else ""

    print(f"Resolving a fetchable URL for {owner}/{repo}/{path}\n")
    for url, label in candidates(owner, repo, path, sha):
        ok, detail = probe(url)
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label:28} {detail}")
        if ok:
            print(f"\nUsing: {url}")
            gh_out = os.getenv("GITHUB_OUTPUT")
            if gh_out:
                with open(gh_out, "a") as f:
                    f.write(f"video_url={url}\n")
            return 0

    print("\nNo host served the video correctly.\n")
    print("Most likely causes:")
    print(f"  1. GitHub Pages is not enabled. Turn it on:")
    print(f"     https://github.com/{owner}/{repo}/settings/pages")
    print(f"     Source = 'Deploy from a branch', Branch = main, Folder = / (root)")
    print(f"  2. The file path is wrong -- check {path} exists on main.")
    print(f"  3. The commit was pushed seconds ago; CDNs need a moment.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
