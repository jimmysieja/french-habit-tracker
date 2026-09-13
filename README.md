# Jimmy's French Habit Tracker

I log every French study session — listening, grammar, vocab, reading, writing,
speaking — in a Google Sheet. This repo reads that sheet and rebuilds the stats
below once a day, so the numbers stay current.

[**Live dashboard**](https://jimmysieja.github.io/french-habit-tracker/) — the
same data, interactive.

<!-- STATS:START -->

<sub>Updated 13 Sep 2026, 09:35 UTC &nbsp;·&nbsp; 104 days tracked &nbsp;·&nbsp; 01 Jun 2026 – 12 Sep 2026</sub>

| Current streak | Longest streak | Consistency | Total time |
|:-:|:-:|:-:|:-:|
| **27** days | **47** days | **96%** | **108** h |

## Study calendar

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/calendar-dark.svg">
  <img alt="Daily study calendar, shaded by minutes studied" src="assets/calendar-light.svg" width="100%">
</picture>
<sub>Darker = more time that day. Hover any day on the [live dashboard](https://jimmysieja.github.io/french-habit-tracker/) for the per-skill breakdown.</sub>

## By skill

| Skill | Total | Time | Days practised |
|:--|--:|--:|--:|
| Listening | 3,453 min | 57.5 h | 81 (78%) |
| Grammar | 235 quizzes | 19.6 h | 66 (63%) |
| Vocab | 6,631 cards | 9.2 h | 57 (55%) |
| Reading | 375 min | 6.2 h | 16 (15%) |
| Writing | 12 prompts | 5.0 h | 9 (9%) |
| Speaking | 635 min | 10.6 h | 26 (25%) |
| **Total** | | **108 h** | |

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
  <img alt="Share of days each skill was practised" src="assets/skills-light.svg" width="100%">
</picture>
<sub>Bar = share of days practised.</sub>

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

| Skill | Last 7 days | vs. previous 7 |
|:--|--:|:--|
| Listening | 151 min | -50% |
| Grammar | 20 quizzes | +11% |
| Vocab | 750 cards | -2% |
| Reading | 20 min | -56% |
| Writing | 0 prompts | -100% |
| Speaking | 0 min | -100% |

<sub>Total time converts counts to minutes: vocab 5s/card · grammar 5min/lesson · writing 25min/prompt. 74 h of that is logged directly.</sub>

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
