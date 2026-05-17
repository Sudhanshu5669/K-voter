# Karuta Top.gg Auto-Voter

Automatically votes for the [Karuta](https://top.gg/bot/646937666251915264/vote) Discord bot on top.gg every **13 hours** using GitHub Actions — no local setup needed after the one-time cookie grab.

## How it works

top.gg uses a GraphQL API (`api.top.gg/graphql`) with a `VoteEntity` mutation for votes. Authentication is handled via your Discord login session cookie (`__Secure-next-auth.session-token`). The workflow runs twice a day (every 13 hours) via GitHub Actions cron and uses the stored cookie to cast the vote on your behalf.

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

The workflow will now run automatically at **00:00 UTC** and **13:00 UTC** every day.

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
