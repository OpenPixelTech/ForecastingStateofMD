# Forecasti# Open Pixel — Maryland Procurement Intelligence Agent

Automated business development pipeline for Maryland state government contracts.

**What it does:**
- Reads the Maryland Procurement Forecast XLS (downloaded from gomdsmallbiz.maryland.gov)
- Pre-filters by web/digital/IT keywords
- Scores opportunities with Claude AI for relevance to Open Pixel's services
- Detects **only new opportunities** vs. the previous run (no duplicate alerts)
- Creates **ClickUp tasks** with email notifications for each new opportunity
- Commits a snapshot back to the repo for change tracking over time

---

## Repo Structure

```
open-pixel-procurement/
├── .github/
│   └── workflows/
│       └── procurement_agent.yml   # GitHub Actions — runs on push + schedule
├── scripts/
│   └── agent.py                    # Main agent script
├── forecasts/
│   └── (drop .xls files here)      # MD Procurement Forecast files
├── reports/
│   └── (auto-generated JSON)       # One report per run, committed by bot
├── procurement_snapshot.json        # Tracks seen opportunities (auto-updated)
├── requirements.txt
├── .env.example
└── README.md
```

---

## One-Time Setup

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/open-pixel-procurement.git
cd open-pixel-procurement
```

### 2. Install dependencies (for local runs)
```bash
pip install -r requirements.txt
```

### 3. Create your `.env` file
```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

### 4. Add GitHub Secrets
Go to: **GitHub repo → Settings → Secrets and variables → Actions → New repository secret**

Add all three:

| Secret Name | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `CLICKUP_API_KEY` | ClickUp → Settings → Apps → API Token |
| `CLICKUP_LIST_ID` | Open your ClickUp list → copy the number from the URL |

---

## Monthly Workflow (How to Use It)

### Step 1 — Download the latest forecast
Go to: https://gomdsmallbiz.maryland.gov/Pages/Forecasting.aspx
Click **Export to Excel**. Save the file.

### Step 2 — Drop the file in the `forecasts/` folder and push
```bash
cp ~/Downloads/ForecastingStofMDMarch2026.xls forecasts/
git add forecasts/
git commit -m "Add March 2026 forecast"
git push
```

**That's it.** GitHub Actions automatically:
1. Detects the new file
2. Runs the agent
3. Creates ClickUp tasks for new opportunities
4. Emails you via ClickUp notifications
5. Commits the updated snapshot back to the repo

### Step 3 — Review your ClickUp tasks
Each task includes:
- Agency, description, estimated value, ad date
- Procurement officer name + email
- Claude's relevance score (1–5) and summary
- Recommended next action

---

## Running Locally

```bash
# Normal run (creates ClickUp tasks for new opportunities)
python scripts/agent.py --file forecasts/ForecastingStofMDMarch2026.xls

# Dry run (score only, no ClickUp tasks created)
python scripts/agent.py --file forecasts/ForecastingStofMDMarch2026.xls --dry-run

# Force process all (ignore snapshot — useful for first run or reset)
python scripts/agent.py --file forecasts/ForecastingStofMDMarch2026.xls --all
```

---

## Automatic Schedule

The agent also runs on a **cron schedule** (1st and 15th of each month at 9am ET)
using whatever forecast file was most recently pushed to the `forecasts/` folder.

You can also trigger it manually any time:
**GitHub → Actions tab → Open Pixel Procurement Agent → Run workflow**

Optional manual inputs:
- **Dry run** — score without creating tasks
- **Force all** — process everything, ignore snapshot

---

## How Update Frequency Works

| Trigger | When |
|---|---|
| Push a new `.xls` to `forecasts/` | Immediately on push |
| Scheduled cron | 1st and 15th of every month |
| Manual trigger | Any time via GitHub Actions UI |

The Maryland forecast database updates **continuously throughout the fiscal year** (July–June),
with the biggest changes in July/August when the new FY forecast is released.
Downloading and pushing a fresh file **bi-weekly** is the recommended cadence.

---

## ClickUp Task Structure

```
🏛️ MD Procurement | [Agency] — [Description]

Agency: Maryland State Treasurer's Office
Description: Provision of IT programming/development support
Estimated Value: $1,000,001 to $5,000,000
Anticipated Ad Date: Q2 (Oct–Dec 2025)
Procurement Method: Competitive Sealed Proposal

Procurement Officer: Kris Chewlin
Email: kchewlin@treasurer.state.md.us

Claude Assessment (Score: 5/5)
This is a direct match for Open Pixel's core web/IT development services...

Next Step: Contact PO directly to express interest before RFP is posted on eMMA.
```

**Priority mapping:**
- Score 4–5 → ClickUp Priority: **High**
- Score 1–3 → ClickUp Priority: **Normal**

---

## Useful Links

| Resource | URL |
|---|---|
| MD Procurement Forecast | https://gomdsmallbiz.maryland.gov/Pages/Forecasting.aspx |
| eMMA (live solicitations) | https://emma.maryland.gov |
| DoIT IT Contracts | https://doit.maryland.gov/contracts |
| Board of Public Works | https://marylandcomptroller.gov/boards/public-works |
| Anthropic Console | https://console.anthropic.com |
| ClickUp API Docs | https://clickup.com/api |
ngStateofMD
Business development script used to assist me in finding future contracting opportunities with the State of Maryland.
