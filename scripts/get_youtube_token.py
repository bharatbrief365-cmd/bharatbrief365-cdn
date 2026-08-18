#!/usr/bin/env python3
"""
Get a YouTube refresh token. Run this ONCE on your own machine.

Needs a Google Cloud OAuth client of type "Desktop app".

    python3 scripts/get_youtube_token.py

If the browser can't reach this machine (remote server, WSL, container),
use manual mode -- it prints a URL, you paste back the redirected address:

    python3 scripts/get_youtube_token.py --manual
"""
import os
import re
import sys
import json
import time
import socket
import argparse
import threading
import http.server
import socketserver
import urllib.parse
import urllib.request
import urllib.error
import webbrowser

SCOPE = "https://www.googleapis.com/auth/youtube.upload"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

result = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Browsers request /favicon.ico alongside the callback. Answer it
        # and keep listening -- consuming it as "the" request was a bug that
        # made this script hang forever.
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if "code" in params:
            result["code"] = params["code"][0]
            body = (b"<html><body style='font:16px sans-serif;padding:40px'>"
                    b"<h2>Authorised.</h2><p>You can close this tab and return "
                    b"to the terminal.</p></body></html>")
        elif "error" in params:
            result["error"] = params["error"][0]
            body = (b"<html><body style='font:16px sans-serif;padding:40px'>"
                    b"<h2>Denied.</h2><p>Check the terminal.</p></body></html>")
        else:
            self.send_response(204)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def free_port(preferred=(8080, 8090, 8123, 9004, 0)):
    """Google requires an exact redirect URI, so try the common ports first."""
    for p in preferred:
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", p))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    raise SystemExit("No free port available.")


def exchange(cid, csec, code, redirect):
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": cid,
        "client_secret": csec,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nToken exchange failed ({e.code}): {body}", file=sys.stderr)
        if "redirect_uri_mismatch" in body:
            print(f"\n  Add this EXACT URI to your OAuth client's "
                  f"'Authorised redirect URIs':\n    {redirect}", file=sys.stderr)
        elif "invalid_client" in body:
            print("\n  Client ID or secret is wrong, or the client is not a "
                  "'Desktop app' type.", file=sys.stderr)
        elif "invalid_grant" in body:
            print("\n  The code expired (they last ~60s) or was already used. "
                  "Just run the script again.", file=sys.stderr)
        raise SystemExit(1)


def finish(cid, csec, tok):
    refresh = tok.get("refresh_token")
    if not refresh:
        print("\nNo refresh_token returned.", file=sys.stderr)
        print("Google only sends one on first consent. Remove the app at",
              file=sys.stderr)
        print("https://myaccount.google.com/permissions and run this again.",
              file=sys.stderr)
        raise SystemExit(1)

    print("\n" + "=" * 62)
    print("PASTE THESE INTO GITHUB SECRETS")
    print("Settings > Secrets and variables > Actions")
    print("=" * 62)
    print(f"\n  YT_CLIENT_ID     = {cid}")
    print(f"  YT_CLIENT_SECRET = {csec}")
    print(f"  YT_REFRESH_TOKEN = {refresh}")
    print("\nIf the consent screen is still in 'Testing' mode this token dies")
    print("in 7 days -- publish the app (Google Auth Platform > Audience).")

    with open("youtube_credentials.txt", "w") as f:
        f.write(f"YT_CLIENT_ID={cid}\nYT_CLIENT_SECRET={csec}\n"
                f"YT_REFRESH_TOKEN={refresh}\n")
    print("\nAlso written to youtube_credentials.txt -- DELETE it after use.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", action="store_true",
                    help="no local server; paste the redirected URL back")
    args = ap.parse_args()

    print("=" * 62)
    print("YOUTUBE REFRESH TOKEN HELPER")
    print("=" * 62)
    print("\nGoogle Cloud Console > APIs & Services > Credentials")
    print("(OAuth client type: Desktop app)\n")

    cid = os.getenv("YT_CLIENT_ID") or input("  Client ID     : ").strip()
    csec = os.getenv("YT_CLIENT_SECRET") or input("  Client Secret : ").strip()
    if not cid or not csec:
        sys.exit("Both values are required.")

    if args.manual:
        redirect = "urn:ietf:wg:oauth:2.0:oob"
        # OOB is deprecated by Google; use the localhost flow and have the
        # user copy the failed-to-load URL out of the address bar instead.
        redirect = "http://localhost:8080"
        url = f"{AUTH_URL}?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect,
            "response_type": "code", "scope": SCOPE,
            "access_type": "offline", "prompt": "consent",
        })
        print("\n1. Open this URL in any browser:\n")
        print(url)
        print("\n2. Approve. The page will fail to load -- that is expected.")
        print("3. Copy the FULL address bar URL and paste it here.\n")
        pasted = input("  Redirected URL: ").strip()
        m = re.search(r"[?&]code=([^&]+)", pasted)
        if not m:
            sys.exit("No ?code= found in that URL.")
        code = urllib.parse.unquote(m.group(1))
        finish(cid, csec, exchange(cid, csec, code, redirect))
        return

    port = free_port()
    redirect = f"http://localhost:{port}"
    url = f"{AUTH_URL}?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent",
    })

    srv = socketserver.TCPServer(("127.0.0.1", port), Handler)
    srv.allow_reuse_address = True
    # serve_forever (not handle_request) so favicon and preflight hits
    # do not consume the one request we actually care about.
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"\nListening on {redirect}")
    print("\nIf the browser does not open, paste this URL yourself:\n")
    print(url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("Waiting for approval (5 min timeout)...")
    print("On 'Google hasn't verified this app': Advanced > Go to ... (unsafe)")
    deadline = time.time() + 300
    while time.time() < deadline and not result:
        time.sleep(0.5)
    srv.shutdown()
    srv.server_close()

    if result.get("error"):
        sys.exit(f"Authorisation denied: {result['error']}")
    if "code" not in result:
        print("\nTimed out. If the browser could not reach localhost "
              "(remote box, WSL, container), retry with:", file=sys.stderr)
        print("    python3 scripts/get_youtube_token.py --manual",
              file=sys.stderr)
        sys.exit(1)

    print("Code received. Exchanging for tokens...")
    finish(cid, csec, exchange(cid, csec, result["code"], redirect))


if __name__ == "__main__":
    main()
