# French habit tracker — analytics

Pulls a language-learning **Daily Log** from Google Sheets and turns it into real
analytics: streaks, trends, skill balance, weekly-objective attainment, and a
rough **"time on French"** estimate that converts card/lesson/prompt counts into
minutes. Ships a text report and a self-contained HTML dashboard.

> Run `python dashboard.py` to build the dashboard locally. Drop a screenshot in
> `docs/dashboard.png` to show it off here.

## What it produces

| Command | Output |
|---|---|
| `python analytics.py` | full text report to the terminal |
| `python analytics.py --push` | writes a summary block into the sheet's Analytics tab |
| `python dashboard.py` | builds `dashboard.html` (streak calendar, rolling-average trends, weekly-vs-target, skill balance, time split, day-of-week) and opens it |
| `python dashboard.py --body-only --out page.html` | headless HTML fragment (e.g. to embed in a website) |

Everything is importable too:

```python
from analytics import load_daily_log, streaks, totals, skill_balance
df = load_daily_log()
print(streaks(df))
```

## Setup

### 1. Install

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Google service account

1. In the [Google Cloud console](https://console.cloud.google.com/) create a
   project, enable the **Google Sheets API** and **Google Drive API**.
2. Create a **service account** and download its **JSON key**.
3. Share your spreadsheet with the service account's email
   (`…@….iam.gserviceaccount.com`) as a **Viewer** (or Editor if you want
   `--push` to work).

### 3. Configure

```bash
cp .env.example .env
```

Then edit `.env`:

```
FR_SERVICE_ACCOUNT=./service-account.json
FR_SHEET_KEY=1AbC…the id from your sheet URL…
```

`.env` and `*.json` are git-ignored — your credentials never get committed.

## The sheet it expects

A tab named **📅Daily Log** with these columns (header row 1):

| Date | Listening (minutes) | Grammar (quizzes) | Vocab (Anki cards) | Reading (minutes) | Writing (Prompts) | Speaking (minutes) | Notes |
|------|------|------|------|------|------|------|------|

Dates like `01 Jun 2026`. Blank cell = 0. Weeks start Monday.

Optional: a **🎯 Weekly Objectives** tab (`Week Starting` + one column per skill)
unlocks the objective-attainment views. An **📈 Analytics** tab receives the
`--push` summary.

## Time-on-French estimate

Count-based skills are converted to minute-equivalents so all six can be compared
by time. Defaults (edit `EST_MIN_PER_UNIT` in `analytics.py`):

| Skill | Assumption |
|---|---|
| Vocab | 5 seconds / card (≈ 25 min per 300 cards) |
| Grammar | 5 minutes / lesson |
| Writing | 25 minutes / prompt (drafting + review) |
| Listening / Reading / Speaking | already minutes |

## Project layout

```
analytics.py    data loading + all metric functions + text report + --push
dashboard.py    renders dashboard.html from analytics.py (hand-built SVG, no deps)
test_connection.py   minimal "can I reach the sheet" check
requirements.txt
.env.example
```

## Roadmap

- [ ] Commit a rendered `dashboard.html` via GitHub Actions on a schedule
- [ ] Publish it to GitHub Pages / embed on a personal site
- [ ] Per-skill streak badges

## License

MIT — see [LICENSE](LICENSE).
