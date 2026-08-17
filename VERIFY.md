# How to verify both things

Two new scripts do the checking for you. Both are **read-only** — neither posts anything.

| Script | Verifies |
|---|---|
| `scripts/verify_setup.py` | Your secrets: token valid, not expiring, right scopes, account is Business |
| `scripts/check_reel.py` | Your video: codec, duration, aspect, faststart |

Add them to the repo alongside the others, plus `.github/workflows/verify-setup.yml`.

---

# Part A — Verify `reel.mp4` (already done — it passes)

Your repo is public, so I ran the real file from your `main` branch:

```
===== VIDEO =====
  Codec       : avc1          (H.264)
  Resolution  : 1080x1920
  Aspect      : 0.5625        (exactly 9:16)
  FPS         : 24.00
===== AUDIO =====
  Codec       : mp4a          (AAC)
  Sample rate : 44100 Hz

  [PASS] Container MP4
  [PASS] Video codec H.264/HEVC
  [PASS] Audio codec AAC
  [PASS] Duration in range                 30.00s
  [PASS] File under 100MB                  1.66 MB
  [PASS] moov atom before mdat (faststart) yes
  [PASS] 9:16 aspect (Reels tab)           1080x1920
  [PASS] Min 540x960
  [PASS] FPS 23-60                         24.00

RESULT: PASS -- meets all Instagram Reels API requirements.
```

**Your video is fine. Nothing to fix.** 30 seconds, 1080×1920, H.264 + AAC, faststart already set — whatever generates it is producing correct output. Cross-checked field-by-field against ffmpeg.

## To re-check it yourself later

No ffmpeg needed — `check_reel.py` parses the MP4 atoms in pure Python:

```bash
python3 scripts/check_reel.py posts/reel.mp4

# or straight from the public URL, no clone required:
python3 scripts/check_reel.py "https://cdn.jsdelivr.net/gh/bharatbrief365-cmd/bharatbrief365-cdn@main/posts/reel.mp4"
```

If you do have ffmpeg, the one-line equivalent:

```bash
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,r_frame_rate \
  -of default=noprint_wrappers=1 posts/reel.mp4
```

Worth re-running whenever the generator changes, since your bot rewrites this file weekly.

---

# Part B — Verify the two secrets

## B1. Confirm they're saved

Repo → **Settings** → **Secrets and variables** → **Actions**. You should see `IG_USER_ID` and `IG_ACCESS_TOKEN` listed under *Repository secrets*.

GitHub never shows values again after saving — only names and an "Updated" date. So seeing the name is the only visual confirmation you get. To check the *values* are right, use B2 or B3.

Common gotchas: a trailing newline or space pasted with the value, and name typos (`IG_TOKEN` vs `IG_ACCESS_TOKEN`) — secrets are case-sensitive.

## B2. Verify from your own machine first

Fastest feedback loop — no commit required:

```bash
export IG_USER_ID="17841400000000000"
export IG_ACCESS_TOKEN="EAAG..."
python3 scripts/verify_setup.py
```

A healthy run:

```
  [ OK ] IG_USER_ID present (1784...000, 17 chars)
  [ OK ] IG_ACCESS_TOKEN present (203 chars)

--- Token ---
  [ OK ] Valid | app_id=1234567890 type=USER
  [ OK ] expires in 59 days (2026-10-16)
  Scopes: instagram_basic, instagram_content_publish, pages_show_list
  [ OK ] Publish scope granted

--- Account ---
  [ OK ] @bharatbrief365 (Bharat Brief)
         media=42 followers=310
  [ OK ] account_type = BUSINESS

--- Publishing ---
  [ OK ] Quota endpoint reachable -- 0/100 posts used in last 24h

RESULT: READY. Secrets are valid and the account can publish.
```

That last section is the one that matters most: `content_publishing_limit` is the same permission surface the real publish uses, so if it succeeds, publishing will too.

## B3. Verify the secrets as GitHub actually sees them

B2 tests what's on your laptop. This tests what's stored in the repo — catches paste errors:

Actions → **Verify Instagram Setup** → **Run workflow**.

It runs four checks: secrets non-empty → token/account valid → video valid → public URL serves `video/mp4`. Exits non-zero on any hard failure.

## Manual one-liners

If you prefer curl:

```bash
# Is the token alive, and when does it die?
curl -s "https://graph.facebook.com/v21.0/debug_token?input_token=$TOK&access_token=$TOK"

# Is IG_USER_ID the right account, and is it BUSINESS?
curl -s "https://graph.facebook.com/v21.0/$UID?fields=username,account_type&access_token=$TOK"

# The real permission test
curl -s "https://graph.facebook.com/v21.0/$UID/content_publishing_limit?access_token=$TOK"
```

---

## Reading the failures

| Output | Meaning |
|---|---|
| `Cannot parse access token` | Token mangled — truncated on paste, or has a stray newline |
| `Token expires in 0 days` | Short-lived token; you skipped the `fb_exchange_token` exchange |
| `Missing instagram_content_publish` | Regenerate the token with that permission ticked |
| `account_type = MEDIA_CREATOR` | Creator account. Must switch to Business — the API rejects Creator |
| `Cannot read account ...` + code 100 | `IG_USER_ID` is your Facebook **Page** ID, not the Instagram account ID |
| `content_publishing_limit failed` | Token works for reads but lacks publish rights — usually App Review |

The Page-ID-instead-of-IG-ID mixup is by far the most common. The fix:

```bash
curl "https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=$TOK"
```

Use the `instagram_business_account.id` from that response — it starts with `1784...` and is ~17 digits.

---

## Order to do things

1. Run `check_reel.py` — **already passing for you**
2. Add the two secrets
3. Run `verify_setup.py` locally (B2)
4. Run the Verify workflow (B3)
5. Only then run **Post Reel to Instagram**

Step 5 is the first thing that touches your actual Instagram feed. Everything before it is safe to run as often as you like.
