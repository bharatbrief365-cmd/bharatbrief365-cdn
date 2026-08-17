# Auto-post your CDN repo's MP4 to Instagram

Publishes `posts/reel.mp4` from your public GitHub repo to Instagram as a Reel, on a schedule or at the push of a button.

**Your public repo is exactly what makes this work.** Instagram does not accept file uploads on this flow — Meta's servers *fetch* the video from a public HTTPS URL. Your `bharatbrief365-cdn` repo already is that URL.

## Files

| File | Purpose |
|---|---|
| `scripts/post_reel.py` | Container → poll → publish, with preflight + quota checks |
| `.github/workflows/post-reel.yml` | Daily schedule + manual run button |
| `.github/workflows/refresh-token.yml` | Monthly token refresh so it doesn't die at day 60 |

Drop these into a repo (the CDN repo itself is fine) and commit.

## Setup — the one-time painful part

The code is easy; Meta's account plumbing is the real work. In order:

1. **Instagram account → Business.** Settings → Account type → Switch to Business. *Creator accounts cannot publish via API.* This is the #1 failure point.
2. **Link it to a Facebook Page.** Required even if you never touch Facebook.
3. **Create a Meta app** at [developers.facebook.com](https://developers.facebook.com) → Business type → add the *Instagram* product.
4. **Get a long-lived token** with `instagram_basic` + `instagram_content_publish`. Use the Graph API Explorer to get a short-lived one, then exchange it (same curl as in `refresh-token.yml`).
5. **Get your IG user ID:**
   ```
   curl "https://graph.facebook.com/v21.0/me/accounts?access_token=TOKEN"
   curl "https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=TOKEN"
   ```
6. **App Review** for `instagram_content_publish` — needed for production. In dev mode it works for admin/test users of the app, which is usually enough if you're only posting to your own account.

### Repo secrets

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `IG_USER_ID` | numeric ID from step 5 |
| `IG_ACCESS_TOKEN` | long-lived token |
| `META_APP_ID` / `META_APP_SECRET` | for auto-refresh only |
| `GH_PAT` | fine-grained PAT, `secrets: write`, for auto-refresh only |

Then edit `CDN_OWNER` / `CDN_REPO` at the top of `post-reel.yml` if the workflow lives in a different repo.

## Run it

Actions tab → **Post Reel to Instagram** → Run workflow. Set a caption inline. Watch the log; the job summary gets the live permalink.

Schedule is `30 12 * * *` = 18:00 IST. Cron in Actions is **always UTC** — subtract 5:30 from your intended IST time. Note GitHub's scheduler is best-effort and can lag 5–15 minutes under load.

## Video specs that actually matter

Your MP4 must satisfy these or the container comes back `ERROR`:

- MP4/MOV, **H.264** video + **AAC** audio, `moov` atom at the front (`-movflags +faststart`)
- **9:16**, min 540×960 — otherwise it won't land in the Reels tab
- **5–90 seconds** via API, regardless of what the phone app allows
- Under 100 MB

Safe re-encode:
```bash
ffmpeg -i in.mp4 -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -r 30 -c:a aac -b:a 128k -ar 48000 -movflags +faststart out.mp4
```

## Why jsDelivr instead of raw.githubusercontent.com

The workflow builds a `cdn.jsdelivr.net/gh/...` URL pinned to the commit SHA. `raw.githubusercontent.com` serves video with headers Meta's fetcher is inconsistent about, and it isn't SHA-pinned, so Meta can grab a cached older file. jsDelivr gives proper `video/mp4`, byte-range support, and immutable per-commit URLs.

## When it breaks

| Symptom | Cause |
|---|---|
| `(#10) Application does not have permission` | Creator account, or `instagram_content_publish` not granted |
| Container stuck `IN_PROGRESS` → `ERROR` | Codec/faststart problem. Re-encode with the ffmpeg line above |
| `Media Posted Before` | Meta dedupes identical files. Change the video, not just the caption |
| Error 24 | Wrong codec, silently. Re-encode |
| Works, then dies ~60 days later | Token expired — that's what `refresh-token.yml` is for |
| Nothing runs after 60 days of no commits | GitHub disables schedules on inactive repos. Your bot's daily commits keep it alive |

Rate limit is 100 API posts per rolling 24h; the script prints your usage before every publish.
