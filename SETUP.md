# Running your own copy

The repo tracks a Google Sheet and republishes the stats. To point it at *your*
sheet you need a Google service account and a few secrets.

## 1. Local install

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
```

## 2. Google service account

1. In the [Google Cloud console](https://console.cloud.google.com/) create a
   project and enable the **Google Sheets API** and **Google Drive API**.
2. Create a **service account**, then add a **JSON key** and download it.
3. Share your spreadsheet with the service account's email
   (`…@….iam.gserviceaccount.com`) — **Viewer** is enough (use **Editor** only if
   you want `analytics.py --push` to write a summary back into the sheet).

## 3. Configure locally

```bash
cp .env.example .env
```

```ini
FR_SERVICE_ACCOUNT=./service-account.json
FR_SHEET_KEY=1AbC…            # the id in the sheet URL: /spreadsheets/d/<THIS>/edit
```

`.env`, `*.json`, `public/` and `dashboard.html` are git-ignored, so credentials
and build output never get committed.

## 4. The sheet layout

A tab named **📅Daily Log**, header in row 1:

| Date | Listening (minutes) | Grammar (quizzes) | Vocab (Anki cards) | Reading (minutes) | Writing (Prompts) | Speaking (minutes) | Notes |
|------|------|------|------|------|------|------|------|

Dates like `01 Jun 2026`. Blank cell = 0. Weeks start Monday. Rows after the last
real entry are ignored, so you can pre-fill dates.

Optional **🎯 Weekly Objectives** tab (`Week Starting` + one column per skill)
turns on the objective-attainment views. Optional **📈 Analytics** tab receives
the `analytics.py --push` summary block.

If your tab names differ, override `FR_DAILY_TAB` / `FR_OBJECTIVES_TAB` /
`FR_ANALYTICS_TAB` in `.env`.

## 5. Run it

```bash
python analytics.py            # text report
python dashboard.py            # build dashboard.html and open it
python build.py               # everything CI does: public/index.html + assets/ + README stats
```

## 6. Automate with GitHub Actions + Pages

1. **Repo → Settings → Secrets and variables → Actions → New repository secret:**
   - `FR_SERVICE_ACCOUNT_JSON` — paste the *entire contents* of your JSON key file
   - `FR_SHEET_KEY` — your sheet id
2. **Repo → Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. The workflow in `.github/workflows/dashboard.yml` runs every 6 hours (and on
   demand from the Actions tab). It rebuilds `public/index.html`, refreshes the
   README stats and `assets/*.svg`, commits any change, and deploys Pages.

Adjust the cadence via the `cron:` line in that workflow.

## Time-on-French conversion rates

Edit `EST_MIN_PER_UNIT` in `analytics.py`:

| Skill | Default |
|---|---|
| Vocab | 5 seconds / card |
| Grammar | 5 minutes / lesson |
| Writing | 25 minutes / prompt |
| Listening / Reading / Speaking | already minutes |

## Files

```
analytics.py    sheet loading + every metric + text report + --push
dashboard.py    hand-built SVG charts -> dashboard.html + standalone asset SVGs
build.py        CI entry point: public/index.html, assets/, README stats block
test_connection.py   "can I reach the sheet" check
.github/workflows/dashboard.yml   schedule -> build -> commit -> deploy Pages
```
