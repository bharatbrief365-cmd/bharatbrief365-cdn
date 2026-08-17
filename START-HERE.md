# START HERE — exactly where each file goes, and what to click

## Part 0 — Where the code goes

Everything goes into **`bharatbrief365-cmd/bharatbrief365-cdn`** — the same repo in your screenshot. Not a new repo.

Why that repo specifically: the workflow runs `git rev-parse HEAD` to build a commit-pinned video URL. It has to be checking out the repo the `reel.mp4` actually lives in, or the SHA points at the wrong thing.

Your repo should end up looking like this (new files marked `NEW`):

```
bharatbrief365-cdn/
├── posts/
│   ├── post_1.jpg ... post_10.jpg
│   └── reel.mp4                        <- already there
├── .github/
│   └── workflows/
│       ├── post-reel.yml               <- NEW
│       └── refresh-token.yml           <- NEW
├── scripts/
│   └── post_reel.py                    <- NEW
└── README.md                           <- already there, leave it
```

> Your repo may already have a `.github/workflows/` folder — that's where the bot's "Auto-generate daily JPEGs" workflow lives. If so, just add the new files alongside the existing ones. Don't delete anything.

---

## Part 1 — Paste the files (browser only, no terminal needed)

Do this three times, once per file.

1. Go to `https://github.com/bharatbrief365-cmd/bharatbrief365-cdn`
2. Click **Add file** (top right) → **Create new file**
3. In the filename box, type the **full path** — typing `/` creates folders automatically:
   - `.github/workflows/post-reel.yml`
   - `.github/workflows/refresh-token.yml`
   - `scripts/post_reel.py`
4. Paste the matching file's contents from this workspace
5. Scroll down → **Commit changes**

Prefer the terminal? From a local clone:

```bash
git add .github/workflows/post-reel.yml .github/workflows/refresh-token.yml scripts/post_reel.py
git commit -m "Add Instagram auto-posting"
git push
```

**One edit to make.** Open `.github/workflows/post-reel.yml` and confirm lines ~34–35 read:

```yaml
CDN_OWNER: bharatbrief365-cmd
CDN_REPO: bharatbrief365-cdn
```

Those are already filled in for you from your screenshot. Only change them if you put the workflow in a different repo than the video.

---

## Part 2 — Meta setup (the slow part: ~30–60 min)

Nothing works until this is done. Do it in order — each step needs the one before it.

### 2.1 Make the Instagram account a Business account
Instagram app → Settings → Account type and tools → Switch to professional account → pick **Business**.

**Not Creator.** Creator accounts cannot publish through the API. If you skip this you'll get `(#10) Application does not have permission` later and it will look like a code bug. It isn't.

### 2.2 Link it to a Facebook Page
Create a Facebook Page if you don't have one (it can be empty and unused), then link it: Instagram → Settings → Sharing to other apps → Facebook.

Required even though you will never post to Facebook.

### 2.3 Create a Meta app
1. [developers.facebook.com](https://developers.facebook.com) → **My Apps** → **Create App**
2. Use case: **Other** → Type: **Business**
3. Name it anything → Create
4. In the app dashboard, find **Instagram** → **Set up**
5. Note your **App ID** and **App Secret** (Settings → Basic) — needed for auto-refresh

### 2.4 Get a token
1. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Top right: select your app
3. **Add permissions**: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`
4. Click **Generate Access Token**, approve the popup
5. Copy the token — this one is short-lived (~1 hour), you'll upgrade it next

Exchange it for a 60-day token (paste into any terminal, filling in the three values):

```bash
curl -sG "https://graph.facebook.com/v21.0/oauth/access_token" \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=YOUR_APP_ID" \
  --data-urlencode "client_secret=YOUR_APP_SECRET" \
  --data-urlencode "fb_exchange_token=YOUR_SHORT_TOKEN"
```

Save the `access_token` from the response. **This is your `IG_ACCESS_TOKEN`.**

### 2.5 Get your Instagram user ID

```bash
# Step A — find your Page ID
curl "https://graph.facebook.com/v21.0/me/accounts?access_token=YOUR_LONG_TOKEN"

# Step B — get the IG account attached to it
curl "https://graph.facebook.com/v21.0/PAGE_ID_FROM_STEP_A?fields=instagram_business_account&access_token=YOUR_LONG_TOKEN"
```

The numeric `instagram_business_account.id` is your **`IG_USER_ID`**.

If step B returns nothing, the Page and Instagram account aren't linked — go back to 2.2.

---

## Part 3 — Add the secrets

In the CDN repo: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.

Add these two now:

| Name | Value |
|---|---|
| `IG_USER_ID` | numeric ID from 2.5 |
| `IG_ACCESS_TOKEN` | long-lived token from 2.4 |

These three are only for the monthly auto-refresh — you can add them later:

| Name | Value |
|---|---|
| `META_APP_ID` | from 2.3 |
| `META_APP_SECRET` | from 2.3 |
| `GH_PAT` | fine-grained PAT with **Secrets: write** on this repo |

Your repo being public is not a problem — GitHub secrets are encrypted and are never exposed to forked-PR builds.

---

## Part 4 — Check your video before the first run

The API is stricter than the Instagram app. Your `reel.mp4` must be:

- H.264 video + AAC audio, MP4
- 9:16, at least 540×960
- **5 to 90 seconds** (hard API limit, regardless of what the app allows)
- Under 100 MB, `moov` atom at the front

Check what you currently have:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,duration \
  -of default=noprint_wrappers=1 posts/reel.mp4
```

If anything is off, re-encode and commit the result:

```bash
ffmpeg -i posts/reel.mp4 -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -r 30 -c:a aac -b:a 128k -ar 48000 -movflags +faststart posts/reel_fixed.mp4
```

Whatever generates your reel weekly should ideally use these same flags going forward.

---

## Part 5 — First run

1. Repo → **Actions** tab
2. Left sidebar → **Post Reel to Instagram**
3. **Run workflow** button (right side) → type a caption → **Run workflow**
4. Click into the run and watch the log

A healthy run prints:

```
Video reachable: 200 | video/mp4 | 8.4 MB
Publishing quota: 0 / 100 in last 24h
Container created: 178414...
  status=IN_PROGRESS
  status=FINISHED
Published! media_id=179922... https://www.instagram.com/reel/...
```

The permalink also lands in the run's summary page.

**Test manually first.** Don't wait for the cron — you want to see it succeed once while you're watching. Once it works, the daily 18:00 IST schedule takes over on its own.

---

## Part 6 — After it works

- **Change the time:** edit the cron in `post-reel.yml`. It's **UTC** — subtract 5:30 from your IST target. `30 12 * * *` = 18:00 IST.
- **Post on new video instead of on a timer:** tell me and I'll swap the trigger to `push` with a path filter on `posts/reel.mp4`.
- **Watch for day 60:** if you skipped the `GH_PAT` secret, the token expires and posting stops silently. Set a calendar reminder or add the refresh secrets.

---

## If the first run fails

| Log message | Fix |
|---|---|
| `Video URL not publicly reachable` | jsDelivr needs a few minutes on a fresh commit. Re-run |
| `(#10) Application does not have permission` | Account is Creator not Business (2.1), or permission missing (2.4) |
| `status=ERROR` after IN_PROGRESS | Codec issue — run the ffmpeg command in Part 4 |
| `Media Posted Before` | Meta dedupes identical files. Needs a genuinely different video |
| `Invalid OAuth access token` | Token expired or wasn't exchanged for the long-lived one |
| Error 24 | Wrong codec, reported unhelpfully. Re-encode |

Paste the failing log line to me and I'll pinpoint it.
