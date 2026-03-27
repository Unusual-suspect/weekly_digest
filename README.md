# Regulatory Intelligence Agent

Weekly EU payments & agentic commerce regulatory briefing.
**Zero cost. No AI APIs. No paid services.**

## How it works

Every Monday at 07:00 CET, GitHub Actions:
1. Fetches 6 RSS feeds directly from primary regulatory sources
2. Filters for relevant keywords (PSD3, AI Act, SCA, agentic payments, etc.)
3. Assigns urgency: Urgent / Act Soon / Watch
4. Sends a styled HTML email via SendGrid (free tier)

## RSS Sources

| Source | Feed |
|---|---|
| EBA | eba.europa.eu |
| European Commission (FISMA) | ec.europa.eu |
| EUR-Lex | eur-lex.europa.eu |
| Finextra | finextra.com |
| ECB Press Releases | ecb.europa.eu |
| Payments & Cards Network | paymentscardsandmobile.com |

## Setup (5 minutes)

### 1. Create a new GitHub repo and push these files
```bash
git init rss-reg-intel
cd rss-reg-intel
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/rss-reg-intel.git
git push -u origin main
```

### 2. Add 3 Secrets
Go to **Settings → Secrets and variables → Actions**

| Secret | Value |
|---|---|
| `SENDGRID_API_KEY` | From app.sendgrid.com |
| `EMAIL_FROM` | Your verified SendGrid sender |
| `EMAIL_TO` | Where to send the digest |

### 3. Run a test
Go to **Actions → Weekly Regulatory Intelligence → Run workflow**

### Local dry run
```bash
pip install -r requirements.txt
export DRY_RUN=1
python agent.py
open preview.html
```

## Customising

**Add more RSS feeds** — add to the `FEEDS` list in `agent.py`

**Add keywords** — add to `KEYWORDS`, `URGENT_KEYWORDS`, or `ACT_SOON_KEYWORDS`

**Change lookback window** — set `LOOKBACK_DAYS` variable in the workflow

## Cost
| Component | Cost |
|---|---|
| GitHub Actions | Free |
| SendGrid | Free (100 emails/day) |
| RSS feeds | Free (public) |
| **Total** | **$0.00/week** |
