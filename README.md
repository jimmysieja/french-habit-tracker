# Jimmy's French Habit Tracker

I log every French study session — listening, grammar, vocab, reading, writing,
speaking — in a Google Sheet. This repo reads that sheet and rebuilds the stats
below once a day, so the numbers stay current.

[**Live dashboard**](https://jimmysieja.github.io/french-habit-tracker/) — the
same data, interactive.

<!-- STATS:START -->

<sub>Updated 30 Oct 2026, 10:54 UTC &nbsp;·&nbsp; 151 days tracked &nbsp;·&nbsp; 01 Jun 2026 – 29 Oct 2026</sub>

| Consistency | Total time | Median weekly time | Last 7 days | Last 30 days |
|:-:|:-:|:-:|:-:|:-:|
| **96%** | **158** h | **7.3** h | **9.2** h | **31.4** h |

## Study calendar

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/calendar-dark.svg">
  <img alt="Daily study calendar, shaded by minutes studied" src="assets/calendar-light.svg" width="100%">
</picture>
<sub>Darker = more time that day. Hover any day on the [live dashboard](https://jimmysieja.github.io/french-habit-tracker/) for the per-skill breakdown.</sub>

## By skill

| Skill | Total | Time | Days practiced |
|:--|--:|--:|--:|
| Listening | 5,058 min | 84.3 h | 124 (82%) |
| Grammar | 415 quizzes | 34.6 h | 97 (64%) |
| Vocab | 10,302 cards | 14.3 h | 86 (57%) |
| Reading | 530 min | 8.8 h | 31 (21%) |
| Writing | 17 prompts | 4.2 h | 14 (9%) |
| Speaking | 715 min | 11.9 h | 35 (23%) |
| **Total** | | **158 h** | |

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
| Listening | 273 min |
| Grammar | 36 quizzes |
| Vocab | 391 cards |
| Reading | 25 min |
| Writing | 0 prompts |
| Speaking | 40 min |

<sub>Total time converts counts to minutes: vocab 5s/card · grammar 5min/lesson · writing 15min/prompt. 105 h of that is logged directly.</sub>

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
