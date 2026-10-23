# Jimmy's French Habit Tracker

I log every French study session — listening, grammar, vocab, reading, writing,
speaking — in a Google Sheet. This repo reads that sheet and rebuilds the stats
below once a day, so the numbers stay current.

[**Live dashboard**](https://jimmysieja.github.io/french-habit-tracker/) — the
same data, interactive.

<!-- STATS:START -->

<sub>Updated 23 Oct 2026, 09:23 UTC &nbsp;·&nbsp; 143 days tracked &nbsp;·&nbsp; 01 Jun 2026 – 21 Oct 2026</sub>

| Consistency | Total time | Median weekly time | Last 7 days | Last 30 days |
|:-:|:-:|:-:|:-:|:-:|
| **96%** | **149** h | **7.3** h | **8.4** h | **32.3** h |

## Study calendar

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/calendar-dark.svg">
  <img alt="Daily study calendar, shaded by minutes studied" src="assets/calendar-light.svg" width="100%">
</picture>
<sub>Darker = more time that day. Hover any day on the [live dashboard](https://jimmysieja.github.io/french-habit-tracker/) for the per-skill breakdown.</sub>

## By skill

| Skill | Total | Time | Days practiced |
|:--|--:|--:|--:|
| Listening | 4,770 min | 79.5 h | 116 (81%) |
| Grammar | 379 quizzes | 31.6 h | 93 (65%) |
| Vocab | 9,911 cards | 13.8 h | 83 (58%) |
| Reading | 500 min | 8.3 h | 25 (17%) |
| Writing | 17 prompts | 4.2 h | 14 (10%) |
| Speaking | 675 min | 11.2 h | 31 (22%) |
| **Total** | | **149 h** | |

## 7-day rolling trend

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/trend-dark.svg">
  <img alt="Seven-day rolling average per skill, whole period" src="assets/trend-light.svg" width="100%">
</picture>

## Weekly totals

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/weekly-dark.svg">
  <img alt="Weekly totals per skill" src="assets/weekly-light.svg" width="100%">
</picture>

## Skill balance

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/skills-dark.svg">
  <img alt="Share of days each skill was practiced" src="assets/skills-light.svg" width="100%">
</picture>
<sub>Bar = share of days practiced.</sub>

## Where the time goes

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/time-split-dark.svg">
  <img alt="Share of estimated study time by skill" src="assets/time-split-light.svg" width="100%">
</picture>

## Average minutes by day of week

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/weekday-dark.svg">
  <img alt="Average minutes studied by day of week" src="assets/weekday-light.svg" width="100%">
</picture>

## Last 7 days

| Skill | Last 7 days |
|:--|--:|
| Listening | 250 min |
| Grammar | 17 quizzes |
| Vocab | 316 cards |
| Reading | 80 min |
| Writing | 3 prompts |
| Speaking | 15 min |

<sub>Total time converts counts to minutes: vocab 5s/card · grammar 5min/lesson · writing 15min/prompt. 99 h of that is logged directly.</sub>

<!-- STATS:END -->

## What's tracked

A daily row per skill, in whatever unit is natural for it: minutes for
listening / reading / speaking, quizzes for grammar, cards for vocab, prompts for
writing. The "estimated time on French" figure rolls the counts back into minutes
with rough conversion rates so all six skills compare on one axis.

## How it's built

`analytics.py` pulls the sheet with [gspread](https://docs.gspread.org/) and does
the maths (streaks, rolling trends, skill balance) in pandas. `dashboard.py` draws every chart as hand-written SVG — no chart library —
and emits both a standalone `index.html` and the light/dark `.svg` files embedded
above. A GitHub Actions workflow runs `build.py` on a schedule, commits the
refreshed stats, and redeploys the dashboard to GitHub Pages.

Want to run your own copy? See **[SETUP.md](SETUP.md)**.

## License

MIT — see [LICENSE](LICENSE).
