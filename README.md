# Jimmy's French Habit Tracker

I log every French study session — listening, grammar, vocab, reading, writing,
speaking — in a Google Sheet. This repo reads that sheet and rebuilds the stats
below once a day, so the numbers stay current.

[**Live dashboard**](https://jimmysieja.github.io/french-habit-tracker/) — the
same data, interactive.

<!-- STATS:START -->

<sub>Updated 04 Sep 2026, 08:53 UTC &nbsp;·&nbsp; 95 days tracked &nbsp;·&nbsp; 01 Jun 2026 – 03 Sep 2026</sub>

| Current streak | Longest streak | Consistency | Total time |
|:-:|:-:|:-:|:-:|
| **18** days | **47** days | **96%** | **101** h |

## Study calendar

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/calendar-dark.svg">
  <img alt="Daily study calendar, shaded by minutes studied" src="assets/calendar-light.svg" width="100%">
</picture>
<sub>Darker = more time that day. Hover any day on the [live dashboard](https://jimmysieja.github.io/french-habit-tracker/) for the per-skill breakdown.</sub>

## By skill

| Skill | Total | Time | Days practised | Weeks on target |
|:--|--:|--:|--:|--:|
| Listening | 3,219 min | 53.6 h | 73 (77%) | 75% |
| Grammar | 215 quizzes | 17.9 h | 59 (62%) | 25% |
| Vocab | 5,670 cards | 7.9 h | 51 (54%) | 33% |
| Reading | 355 min | 5.9 h | 15 (16%) | 8% |
| Writing | 12 prompts | 5.0 h | 9 (9%) | 17% |
| Speaking | 635 min | 10.6 h | 26 (27%) | 50% |
| **Total** | | **101 h** | | |

## 7-day rolling trend

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/trend-dark.svg">
  <img alt="Seven-day rolling average per skill, whole period" src="assets/trend-light.svg" width="100%">
</picture>

## Weekly totals against objective

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/objectives-dark.svg">
  <img alt="Weekly totals per skill with the objective line" src="assets/objectives-light.svg" width="100%">
</picture>

## Skill balance

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/skills-dark.svg">
  <img alt="Share of days each skill was practised" src="assets/skills-light.svg" width="100%">
</picture>
<sub>Bar = share of days practised. Tick = average weekly-objective attainment.</sub>

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
| Listening | 260 min | -10% |
| Grammar | 18 quizzes | +100% |
| Vocab | 792 cards | +3% |
| Reading | 45 min | — |
| Writing | 2 prompts | +100% |
| Speaking | 90 min | +50% |

<sub>Total time converts counts to minutes: vocab 5s/card · grammar 5min/lesson · writing 25min/prompt. 70 h of that is logged directly.</sub>

<!-- STATS:END -->

## What's tracked

A daily row per skill, in whatever unit is natural for it: minutes for
listening / reading / speaking, quizzes for grammar, cards for vocab, prompts for
writing. Weekly objectives sit alongside so I can see where I'm keeping pace and
where I'm slipping. The "estimated time on French" figure rolls the counts back
into minutes with rough conversion rates so all six skills compare on one axis.

## How it's built

`analytics.py` pulls the sheet with [gspread](https://docs.gspread.org/) and does
the maths (streaks, rolling trends, skill balance, objective attainment) in
pandas. `dashboard.py` draws every chart as hand-written SVG — no chart library —
and emits both a standalone `index.html` and the light/dark `.svg` files embedded
above. A GitHub Actions workflow runs `build.py` on a schedule, commits the
refreshed stats, and redeploys the dashboard to GitHub Pages.

Want to run your own copy? See **[SETUP.md](SETUP.md)**.

## License

MIT — see [LICENSE](LICENSE).
