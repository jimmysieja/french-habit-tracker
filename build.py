"""
CI build step. Regenerates everything that gets published:

  public/index.html   - the standalone dashboard (deployed to GitHub Pages)
  assets/*.svg        - light+dark chart files embedded in the README
  README.md           - the block between <!-- STATS:START --> and <!-- STATS:END -->

Run locally the same way CI does:

    python build.py

Environment (all optional locally; set by the workflow in CI):
  GITHUB_REPOSITORY   "owner/name" -> used to derive the Pages URL
  REPO_URL            explicit repo URL (overrides the above)
  SITE_URL            explicit published site URL
"""

from __future__ import annotations

import os
import datetime as dt
from pathlib import Path

import analytics as A
import dashboard as D

ROOT = Path(__file__).parent
MARK_START = "<!-- STATS:START -->"
MARK_END = "<!-- STATS:END -->"


# --------------------------------------------------------------------------- #
# derive the public URLs from the CI environment
# --------------------------------------------------------------------------- #
def _urls() -> tuple[str, str]:
    repo = os.environ.get("REPO_URL", "").rstrip("/")
    site = os.environ.get("SITE_URL", "").rstrip("/")
    gh = os.environ.get("GITHUB_REPOSITORY", "")
    if gh and "/" in gh:
        owner, name = gh.split("/", 1)
        repo = repo or f"https://github.com/{owner}/{name}"
        if not site:
            site = (
                f"https://{owner}.github.io"
                if name.lower() == f"{owner.lower()}.github.io"
                else f"https://{owner}.github.io/{name}"
            )
    return repo, site


# --------------------------------------------------------------------------- #
# the auto-generated README section
# --------------------------------------------------------------------------- #
def _picture(name: str, alt: str) -> str:
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">\n'
        f'  <img alt="{alt}" src="assets/{name}-light.svg" width="100%">\n'
        "</picture>"
    )


def stats_markdown(df, obj) -> str:
    s = A.streaks(df)
    t = A.totals(df)
    m = A.momentum(df)
    bal = A.skill_balance(df, obj)
    est_total = t["est_hours"].sum()
    logged = t["hours"].dropna().sum()
    start, end = df.index[0].date(), df.index[-1].date()
    updated = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    longest = s["longest"][2] if s["longest"] else 0

    L: list[str] = []
    L.append(f"<sub>Updated {updated} &nbsp;·&nbsp; {len(df)} days tracked &nbsp;·&nbsp; "
             f"{start:%d %b %Y} – {end:%d %b %Y}</sub>")
    L.append("")

    # compact summary strip
    L.append("| Current streak | Longest streak | Consistency | Total time |")
    L.append("|:-:|:-:|:-:|:-:|")
    L.append(f"| **{s['current']}** days | **{longest}** days "
             f"| **{s['consistency_pct']:.0f}%** | **{est_total:.0f}** h |")
    L.append("")

    L.append("## Study calendar")
    L.append("")
    L.append(_picture("calendar", "Daily study calendar, shaded by minutes studied"))
    L.append("<sub>Darker = more time that day. Hover any day on the "
             "[live dashboard](https://jimmysieja.github.io/french-habit-tracker/) "
             "for the per-skill breakdown.</sub>")
    L.append("")

    L.append("## By skill")
    L.append("")
    L.append("| Skill | Total | Time | Days practised | Weeks on target |")
    L.append("|:--|--:|--:|--:|--:|")
    for sk in A.SKILLS:
        r = t.loc[sk]
        hit = bal.loc[sk].get("obj_weeks_hit_pct", float("nan"))
        hit_s = "—" if hit != hit else f"{hit:.0f}%"
        L.append(
            f"| {sk} | {r['total']:,.0f} {A.UNIT[sk]} | {r['est_hours']:.1f} h "
            f"| {int(r['days_practiced'])} ({100*r['days_practiced']/len(df):.0f}%) | {hit_s} |"
        )
    L.append(f"| **Total** | | **{est_total:.0f} h** | | |")
    L.append("")

    L.append("## 7-day rolling trend")
    L.append("")
    L.append(_picture("trend", "Seven-day rolling average per skill, whole period"))
    L.append("")

    L.append("## Weekly totals against objective")
    L.append("")
    L.append(_picture("objectives", "Weekly totals per skill with the objective line"))
    L.append("")

    L.append("## Skill balance")
    L.append("")
    L.append(_picture("skills", "Share of days each skill was practised"))
    L.append("<sub>Bar = share of days practised. Tick = average weekly-objective attainment.</sub>")
    L.append("")

    L.append("## Where the time goes")
    L.append("")
    L.append(_picture("time-split", "Share of estimated study time by skill"))
    L.append("")

    L.append("## Average minutes by day of week")
    L.append("")
    L.append(_picture("weekday", "Average minutes studied by day of week"))
    L.append("")

    L.append("## Last 7 days")
    L.append("")
    L.append("| Skill | Last 7 days | vs. previous 7 |")
    L.append("|:--|--:|:--|")
    for sk in A.SKILLS:
        r = m.loc[sk]
        wow = r["wow_change_pct"]
        delta = "—" if wow != wow else (("+" if wow >= 0 else "") + f"{wow:.0f}%")
        L.append(f"| {sk} | {r['last_7d_total']:,.0f} {A.UNIT[sk]} | {delta} |")
    L.append("")
    L.append(
        f"<sub>Total time converts counts to minutes: "
        f"vocab {A.EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card · "
        f"grammar {A.EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson · "
        f"writing {A.EST_MIN_PER_UNIT['Writing']:.0f}min/prompt. "
        f"{logged:.0f} h of that is logged directly.</sub>"
    )
    return "\n".join(L)


def update_readme(df, obj, path: Path | None = None) -> bool:
    path = path or (ROOT / "README.md")
    text = path.read_text(encoding="utf-8")
    if MARK_START not in text or MARK_END not in text:
        raise SystemExit(f"{path.name} is missing the {MARK_START} / {MARK_END} markers")
    head, _, rest = text.partition(MARK_START)
    _, _, tail = rest.partition(MARK_END)
    new = f"{head}{MARK_START}\n\n{stats_markdown(df, obj)}\n\n{MARK_END}{tail}"
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


# --------------------------------------------------------------------------- #
def main() -> None:
    repo_url, _site_url = _urls()
    if repo_url:
        os.environ["REPO_URL"] = repo_url  # picked up by dashboard.page_body()

    df = A.load_daily_log()
    try:
        obj = A.load_objectives()
    except Exception as e:  # noqa: BLE001
        print(f"(objectives unavailable: {e})")
        obj = None

    public = ROOT / "public"
    public.mkdir(exist_ok=True)
    (public / "index.html").write_text(D.build_html(df, obj), encoding="utf-8")
    (public / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {public/'index.html'}")

    written = D.export_assets(df, obj, ROOT / "assets")
    print(f"wrote {len(written)} chart svgs to assets/")

    changed = update_readme(df, obj)
    print("README.md updated" if changed else "README.md already current")


if __name__ == "__main__":
    main()
