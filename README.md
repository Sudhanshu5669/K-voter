# Karuta Top.gg Auto-Voter

Automatically votes for the [Karuta](https://top.gg/bot/646937666251915264/vote) Discord bot on top.gg every **12 hours** using GitHub Actions — scheduled to run every **6 hours** for fail-safe redundancy.

## How it works

top.gg uses a GraphQL API (`api.top.gg/graphql`) with a `VoteEntity` mutation for votes. Authentication is handled via your Discord login session cookie (`__Secure-next-auth.session-token`). The workflow runs four times a day (every 6 hours) via GitHub Actions cron and uses the stored cookie to cast the vote on your behalf. If you've already voted within the 12-hour cooldown window, the script safely skips the run to avoid duplicate votes without failing your workflow history.

## One-time Setup

### 1. Get your session cookie

1. Log into [top.gg](https://top.gg) via Discord
2. Navigate to the [Karuta vote page](https://top.gg/bot/646937666251915264/vote)
3. Open DevTools → **Application** tab → **Cookies** → `https://top.gg`
4. Find the cookie named `__Secure-next-auth.session-token`
5. Copy its **value** (it's a long string, looks like a JWT)

### 2. Add it as a GitHub Actions Secret

1. Go to your repository on GitHub
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `TOPGG_SESSION_TOKEN`
5. Value: *(paste the cookie value you copied)*
6. Click **Add secret**

### 3. Push this repo to GitHub

```bash
git add .
git commit -m "setup karuta voter"
git push
```

The workflow will now run automatically at **00:00 UTC**, **06:00 UTC**, **12:00 UTC**, and **18:00 UTC** every day (running every 6 hours for safety and redundancy).

## Manual trigger

You can also trigger the vote manually at any time:
- Go to your repo → **Actions** → **Karuta Top.gg Auto-Voter** → **Run workflow**

## When your cookie expires

top.gg session cookies typically last **30 days**. When the vote starts failing, repeat step 1 to get a fresh cookie and update the secret.

> **Tip:** You can monitor runs in the **Actions** tab. The script logs the vote result clearly — `✅ Vote cast!` on success or a descriptive error if something goes wrong.

## Files

| File | Purpose |
|------|---------|
| `vote.py` | Core voting script |
| `.github/workflows/vote.yml` | GitHub Actions cron workflow |
