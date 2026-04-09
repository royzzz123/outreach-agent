# Outreach Agent — Setup Guide

AI-powered lead discovery agent for a text-to-SQL consultancy.
Finds companies hiring data roles, researches them, and surfaces why to reach out — with contact details.

---

## What You'll Need

| Requirement | Where to get it | Cost |
|---|---|---|
| Python 3.10+ | [python.org](https://python.org) | Free |
| MiniMax API key | [minimaxi.chat](https://www.minimaxi.chat) | Pay per use |
| SerpAPI key | [serpapi.com](https://serpapi.com) | 100 searches/month free |
| Hunter.io key | [hunter.io](https://hunter.io) | 25 searches/month free |

---

## 1. Clone / Copy the Project

```bash
# If using git
git clone <your-repo-url>
cd "outreach  Agent"

# Or just copy the folder to your machine, then:
cd "outreach  Agent"
```

---

## 2. Create a Virtual Environment

```bash
python3 -m venv venv

# Activate it:
# macOS / Linux
source venv/bin/activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1

# Windows (CMD)
venv\Scripts\activate.bat
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Then install the Playwright browser (used for LinkedIn DM automation — optional):

```bash
playwright install chromium
```

---

## 4. Configure Environment Variables

Copy the example file and fill it in:

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in your keys:

```env
# ── Required ───────────────────────────────────────────────
MINIMAX_API_KEY=sk-cp-your-key-here
MINIMAX_MODEL=MiniMax-M2

SERP_API_KEY=your-serpapi-key
HUNTER_API_KEY=your-hunter-key

# ── Your pitch (injected into outreach messages) ───────────
SENDER_NAME=Your Name
SENDER_ROLE=Founder
WEBSITE_URL=https://yoursite.com
PITCH_PDF_URL=https://drive.google.com/your-pitch.pdf
CAL_LINK=https://cal.com/yourname/discovery

# ── Optional: email sending ────────────────────────────────
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# ── Optional: LinkedIn DM automation ──────────────────────
LINKEDIN_EMAIL=you@email.com
LINKEDIN_PASSWORD=your-password
```

### Getting each key

**MiniMax API key**
1. Sign up at [minimaxi.chat](https://www.minimaxi.chat)
2. Go to API Keys → Create new key
3. Paste it as `MINIMAX_API_KEY`

**SerpAPI key**
1. Sign up at [serpapi.com](https://serpapi.com)
2. Dashboard → API Key (shown on first login)
3. Free tier gives 100 searches/month — enough for ~10 agent runs

**Hunter.io key**
1. Sign up at [hunter.io](https://hunter.io)
2. Dashboard → API → copy your key
3. Free tier gives 25 searches/month

**Gmail App Password** (only if you want email sending)
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select app: Mail → Select device: Other → name it "Outreach Agent"
3. Copy the 16-character password (with spaces) into `GMAIL_APP_PASSWORD`
4. Note: requires 2-Step Verification to be enabled on your Google account

---

## 5. Verify the Setup

```bash
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from openai import OpenAI; import os

client = OpenAI(
    api_key=os.getenv('MINIMAX_API_KEY'),
    base_url='https://api.minimaxi.chat/v1',
)
resp = client.chat.completions.create(
    model='MiniMax-M2',
    messages=[{'role': 'user', 'content': 'Reply: connected OK'}],
    max_tokens=50,
)
print(resp.choices[0].message.content)
"
```

Expected output: `connected OK`

---

## 6. Run the Agent

```bash
# Discover leads (dry run — no emails sent)
python agent.py --query "Analytics Engineer" --location "United States" --max-leads 10
```

Other useful queries:
```bash
python agent.py --query "SQL Developer" --max-leads 15
python agent.py --query "BI Developer" --location "New York" --max-leads 10
python agent.py --query "Data Analyst" --location "London" --max-leads 10
python agent.py --query "Head of Data" --max-leads 5
```

Leads are saved to `data/leads.csv` after each one is processed (atomic — safe to Ctrl+C).

---

## 7. View the Dashboard

In a separate terminal:

```bash
python server.py
```

Open your browser at **http://localhost:5050**

The dashboard auto-refreshes every 15 seconds while the agent is running.

---

## Project Structure

```
outreach  Agent/
├── agent.py            # Main agent loop (MiniMax M2 + tool use)
├── tools.py            # Tool implementations (search, scrape, enrich, save)
├── config.py           # Config loaded from .env
├── server.py           # Local web server for the dashboard
├── requirements.txt    # Python dependencies
├── .env.example        # Template — copy to .env and fill in
├── .env                # Your actual keys — never commit this
├── architecture.xml    # Draw.io architecture diagram
├── frontend/
│   └── index.html      # Leads dashboard UI
└── data/
    └── leads.csv       # Output — all discovered leads
```

---

## How It Works (Agent Flow)

```
User runs: python agent.py --query "Analytics Engineer"
    │
    ▼
search_linkedin_jobs()
    └─ SerpAPI → Google Jobs → returns list of companies hiring the role
    │
    ▼  (for each company, one at a time)
scrape_company_website()
    └─ requests + BeautifulSoup → product description + tech stack
    │
    ▼
find_decision_maker()
    └─ Hunter.io domain search → CTO / VP Eng / Head of Data email + LinkedIn
    │
    ▼
analyze_and_save_lead()   ← atomic: analysis + CSV write in one step
    └─ MiniMax M2 → reason to reach out + fit score (1–10)
    └─ Immediately writes to data/leads.csv
    │
    ▼
Dashboard at localhost:5050 shows all leads live
```

---

## Dashboard Columns

| Column | What it shows |
|---|---|
| **Company / Contact** | Company name, website, contact person name + title |
| **Fit** | Score 1–10 (green=8–10, yellow=5–7, red=1–4) |
| **Why Reach Out** | AI-written reason specific to their job posting + tech stack |
| **Email / Phone** | Clickable email + phone if found |
| **LinkedIn** | Blue "View Profile" button linking to the contact's LinkedIn |
| **Job Signal** | The job title that triggered the lead + link to posting |
| **Tech Stack** | Tools detected on their website (Tableau, Snowflake, etc.) |

---

## Troubleshooting

**`MINIMAX_API_KEY not set` error**
- Make sure `.env` exists (not just `.env.example`)
- Make sure you activated the virtual environment before running

**`No contacts found` for most companies**
- Hunter.io free tier has 25 searches/month — you may have hit the limit
- Check your usage at [hunter.io/users/usage](https://hunter.io/users/usage)

**Website scraping returns errors**
- Some sites block scrapers — this is normal, the agent moves on
- The agent still saves the lead with partial data (job info + any contact found)

**SerpAPI returns 0 results**
- Check your remaining credits at [serpapi.com/dashboard](https://serpapi.com/dashboard)
- Try a different query — "SQL Developer" returns more results than niche roles

**LinkedIn DM automation blocked**
- LinkedIn detects automation aggressively
- Keep DMs to max 20/day and use a warmed-up account (not brand new)
- If you hit a checkpoint/CAPTCHA, LinkedIn DMs won't work — use email only

**`playwright install` fails**
- Run: `pip install playwright` then `python -m playwright install chromium`
- On Ubuntu/Debian you may also need: `playwright install-deps chromium`

---

## To View the Architecture Diagram

1. Go to [app.diagrams.net](https://app.diagrams.net)
2. File → Import from → Device
3. Select `architecture.xml`
