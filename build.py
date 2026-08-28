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
from urllib.parse import quote

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
def _badge(label: str, message: str, color: str) -> str:
    q = lambda s: quote(str(s), safe="")
    return f"![{label}](https://img.shields.io/badge/{q(label)}-{q(message)}-{color})"


def _picture(name: str, alt: str) -> str:
    return (
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/{name}-dark.svg">\n'
        f'  <img alt="{alt}" src="assets/{name}-light.svg" width="100%">\n'
        "</picture>"
    )


def stats_markdown(df, obj, site_url: str) -> str:
    s = A.streaks(df)
    t = A.totals(df)
    m = A.momentum(df)
    bal = A.skill_balance(df, obj)
    est_total = t["est_hours"].sum()
    start, end = df.index[0].date(), df.index[-1].date()
    updated = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    L: list[str] = []
    L.append(f"_Auto-updated {updated} — covering {start:%d %b %Y} → {end:%d %b %Y}._")
    L.append("")
    L.append(" ".join([
        _badge("streak", f"{s['current']} days", "2a78d6"),
        _badge("longest", f"{s['longest'][2] if s['longest'] else 0} days", "1baf7a"),
        _badge("time on French", f"{est_total:.0f} h", "eb6834"),
        _badge("days tracked", f"{s['tracked_days']}", "8957e5"),
        _badge("consistency", f"{s['consistency_pct']:.0f}%", "eda100"),
    ]))
    L.append("")
    if site_url:
        L.append(f"**[▶ Open the full interactive dashboard]({site_url}/)**")
        L.append("")

    # headline
    live = "still going" if s["current_live"] else "ended"
    L.append("### At a glance")
    L.append("")
    L.append("| | |")
    L.append("|--|--|")
    L.append(f"| 🔥 Current streak | **{s['current']} days** ({live}) |")
    L.append(f"| 🏆 Longest streak | **{s['longest'][2] if s['longest'] else 0} days** "
             f"({s['longest'][0]:%d %b} – {s['longest'][1]:%d %b}) |" if s["longest"]
             else "| 🏆 Longest streak | — |")
    L.append(f"| 📆 Active days | **{s['active_days']} / {s['tracked_days']}** "
             f"({s['consistency_pct']:.0f}%) |")
    L.append(f"| ⏱ Estimated time on French | **~{est_total:.0f} hours** "
             f"({t['hours'].dropna().sum():.0f} h logged directly) |")
    L.append("")

    # calendar
    L.append("### 📅 Study calendar")
    L.append("")
    L.append(_picture("calendar", "Daily study calendar, shaded by minutes studied"))
    L.append("")

    # by skill
    L.append("### 📊 By skill")
    L.append("")
    L.append("| Skill | Total | Est. time | Days practised | Weeks hit target |")
    L.append("|-------|------:|----------:|---------------:|-----------------:|")
    for sk in A.SKILLS:
        r = t.loc[sk]
        hit = bal.loc[sk].get("obj_weeks_hit_pct", float("nan"))
        hit_s = "—" if hit != hit else f"{hit:.0f}%"
        L.append(
            f"| {sk} | {r['total']:,.0f} {A.UNIT[sk]} | {r['est_hours']:.1f} h "
            f"| {int(r['days_practiced'])} ({100*r['days_practiced']/len(df):.0f}%) | {hit_s} |"
        )
    L.append("")

    # time split + weekday
    L.append("### ⚖️ Where the time goes  ·  📆 By weekday")
    L.append("")
    L.append(_picture("time-split", "Share of estimated study time by skill"))
    L.append("")
    L.append(_picture("weekday", "Average minutes studied by day of week"))
    L.append("")

    # momentum
    L.append("### 🚀 Last 7 days")
    L.append("")
    L.append("| Skill | Last 7 days | vs. previous 7 |")
    L.append("|-------|------------:|:--------------|")
    for sk in A.SKILLS:
        r = m.loc[sk]
        wow = r["wow_change_pct"]
        if wow != wow:
            delta = "—"
        else:
            delta = ("▲ +" if wow >= 0 else "▼ ") + f"{wow:.0f}%"
        L.append(f"| {sk} | {r['last_7d_total']:,.0f} {A.UNIT[sk]} | {delta} |")
    L.append("")
    L.append(f"<sub>Estimated time converts counts to minutes: "
             f"vocab {A.EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card, "
             f"grammar {A.EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson, "
             f"writing {A.EST_MIN_PER_UNIT['Writing']:.0f}min/prompt.</sub>")
    return "\n".join(L)


def update_readme(df, obj, site_url: str, path: Path | None = None) -> bool:
    path = path or (ROOT / "README.md")
    text = path.read_text(encoding="utf-8")
    if MARK_START not in text or MARK_END not in text:
        raise SystemExit(f"{path.name} is missing the {MARK_START} / {MARK_END} markers")
    head, _, rest = text.partition(MARK_START)
    _, _, tail = rest.partition(MARK_END)
    new = f"{head}{MARK_START}\n\n{stats_markdown(df, obj, site_url)}\n\n{MARK_END}{tail}"
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


# --------------------------------------------------------------------------- #
def main() -> None:
    repo_url, site_url = _urls()
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

    changed = update_readme(df, obj, site_url)
    print("README.md updated" if changed else "README.md already current")


if __name__ == "__main__":
    main()
