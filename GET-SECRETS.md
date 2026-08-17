# Where to get `IG_USER_ID` and `IG_ACCESS_TOKEN`

Neither value exists yet — you **create** them at [developers.facebook.com](https://developers.facebook.com). They are not in Instagram's settings and not in GitHub.

| Secret | What it actually is | Looks like |
|---|---|---|
| `IG_USER_ID` | Numeric ID of your Instagram Business account | `17841405793187218` (~17 digits) |
| `IG_ACCESS_TOKEN` | Long-lived token proving your app may post | `EAAGm0PX4ZCpsBA...` (150–250 chars) |

Budget 30–45 minutes. Steps 0–3 are the slow part; step 4 is one command.

---

## Step 0 — Instagram must be a Business account

Instagram app → **Settings and privacy** → **Account type and tools** → **Switch to professional account** → choose **Business**.

If it already says professional, confirm it says **Business** and not Creator.

> **This is the #1 thing that breaks everything.** Creator accounts cannot publish through the API. If you skip it, you get `(#10) Application does not have permission` in step 4 and it looks like a code bug. It isn't. Do this first.

## Step 1 — Link it to a Facebook Page

The API reaches Instagram *through* a Facebook Page. Required even though you'll never post to Facebook.

1. Create a Page at [facebook.com/pages/create](https://www.facebook.com/pages/create) if you don't have one — it can be empty, any name, and stay unpublished
2. Instagram app → Settings → **Accounts Centre** → **Connected experiences** → **Accounts** → add the Facebook Page

Verify: Facebook Page → Settings → **Linked accounts** → Instagram should show as connected.

## Step 2 — Create a Meta app

1. Go to [developers.facebook.com/apps](https://developers.facebook.com/apps) → **Create App**
   - First visit: register as a developer (free, needs phone verification)
2. Use case: **Other** → Next
3. App type: **Business** → Next
4. Name it (e.g. "bharatbrief-poster"), pick your Business Portfolio → **Create app**
5. In the dashboard, find **Instagram** in the product list → **Set up**

**Grab your App ID and Secret now** — left sidebar → **App settings** → **Basic**:
- **App ID** — visible
- **App Secret** — click **Show**

Keep both handy for step 4.

## Step 3 — Generate a short-lived token

1. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. **Meta App** dropdown (top right) → select your app
3. **User or Page** dropdown → **User Token**
4. Click **Add permissions** / **Permissions** and tick all four:
   - `instagram_basic`
   - `instagram_content_publish` ← the one that matters
   - `pages_show_list`
   - `pages_read_engagement`
5. Click **Generate Access Token**
6. A Facebook popup opens — approve, and **make sure your Page and Instagram account are ticked** in the selection screens
7. Copy the token from the box

This one dies in about **1 hour**. That's expected — step 4 upgrades it. Don't put this one in GitHub.

## Step 4 — Turn those into your two secrets

Run the helper script from the repo:

```bash
python3 scripts/get_credentials.py
```

It prompts for App ID, App Secret, and the short-lived token (secret and token are hidden as you type), then:

1. Exchanges the 1-hour token for a **60-day** one
2. Checks the publish scope is actually granted
3. Lists your Pages and finds the linked Instagram account
4. Prints both values ready to paste

Output looks like:

```
[1/3] Exchanging for a long-lived (60-day) token...
      Got it. Valid ~60 days. (203 chars)
      Scopes: instagram_basic, instagram_content_publish, pages_show_list

[2/3] Listing your Facebook Pages...
      - Bharat Brief (Page ID 102938475610293)

[3/3] Looking for linked Instagram Business accounts...
      FOUND: @bharatbrief365 (ID 17841405793187218) via Page 'Bharat Brief'
             type=BUSINESS media=42 followers=310

================================================================
PASTE THESE INTO GITHUB SECRETS
================================================================

  Name : IG_USER_ID
  Value: 17841405793187218

  Name : IG_ACCESS_TOKEN
  Value: EAAGm0PX4ZCpsBA...
```

**Run it in under an hour** of generating the short-lived token, or it'll have expired.

### Doing it by hand instead

```bash
# 4a. Upgrade the token (copy access_token from the response)
curl -sG "https://graph.facebook.com/v21.0/oauth/access_token" \
  --data-urlencode "grant_type=fb_exchange_token" \
  --data-urlencode "client_id=YOUR_APP_ID" \
  --data-urlencode "client_secret=YOUR_APP_SECRET" \
  --data-urlencode "fb_exchange_token=YOUR_SHORT_TOKEN"

# 4b. Find your Page ID
curl -s "https://graph.facebook.com/v21.0/me/accounts?access_token=LONG_TOKEN"

# 4c. Get the Instagram account ID on that Page
curl -s "https://graph.facebook.com/v21.0/PAGE_ID?fields=instagram_business_account&access_token=LONG_TOKEN"
```

`IG_USER_ID` = the `instagram_business_account.id` from 4c — **not** the Page ID from 4b. Mixing these two up is the most common mistake; they're both long numbers.

## Step 5 — Save them in GitHub

1. `https://github.com/bharatbrief365-cmd/bharatbrief365-cdn`
2. **Settings** (repo settings, not your profile)
3. Left sidebar → **Secrets and variables** → **Actions**
4. **New repository secret**
5. Name `IG_USER_ID`, paste the value → **Add secret**
6. **New repository secret** again → `IG_ACCESS_TOKEN` → **Add secret**

Optionally add `META_APP_ID` and `META_APP_SECRET` for the monthly auto-refresh.

Watch for: no spaces or newlines around the pasted value; names are case-sensitive and must match exactly.

Your repo being public is fine — secrets are encrypted, hidden in logs, and unavailable to forked-PR builds.

**If you ran the script, delete `credentials.txt` now.** Never commit it.

```bash
rm credentials.txt
```

## Step 6 — Confirm it all works

```bash
python3 scripts/verify_setup.py
```

Then, to test what GitHub actually stored: Actions → **Verify Instagram Setup** → **Run workflow**. Both are read-only.

Want it to say `RESULT: READY.` before you post for real.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No Pages listed in step 4 | Page not linked (step 1), or Page wasn't ticked in the step 3 popup. Re-link, then regenerate the token |
| `no Instagram Business account` | Still a Personal/Creator account (step 0), or link didn't take |
| `Invalid OAuth access token` | Short-lived token expired. Regenerate in Graph Explorer and re-run within the hour |
| `instagram_content_publish` missing from scopes | Not ticked in step 3, or unticked in the consent popup. Regenerate |
| `Invalid Client ID` | App ID/Secret typo — recopy from App settings → Basic |
| Everything reads fine but publishing 403s | Needs **App Review** for production. In dev mode it works for admin/developer/tester users of the app — enough if you only post to your own account. Add yourself under App roles |

## After 60 days

The token expires and posting stops silently. Either re-run `get_credentials.py` and update the secret, or add `META_APP_ID`, `META_APP_SECRET` and a `GH_PAT` so `refresh-token.yml` rotates it monthly on its own.
