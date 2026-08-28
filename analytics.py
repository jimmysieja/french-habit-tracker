"""
French habit tracker - analytics.

Pulls the Daily Log (and Weekly Objectives) from the Google Sheet and computes
streaks, trends, skill balance, and objective attainment.

    python analytics.py            # print the full text report
    python analytics.py --push     # also write results into the Analytics tab

Everything is also importable:

    from analytics import load_daily_log, build_report
    df = load_daily_log()
"""

from __future__ import annotations

import os
import sys
import io
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import gspread

# make stdout utf-8 on the Windows console so emoji/accents don't blow up
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:  # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def _load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env reader (no dependency). KEY=VALUE lines, # comments."""
    p = Path(path)
    if not p.is_file():
        p = Path(__file__).with_name(".env")
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# Credentials & sheet id come from the environment (or a local `.env` file next
# to this script) so nothing secret is committed. Copy .env.example to .env.
SERVICE_ACCOUNT = os.environ.get(
    "FR_SERVICE_ACCOUNT",
    str(Path(__file__).with_name("service-account.json")),
)
SHEET_KEY = os.environ.get("FR_SHEET_KEY", "")

DAILY_TAB = os.environ.get("FR_DAILY_TAB", "📅Daily Log")
OBJECTIVES_TAB = os.environ.get("FR_OBJECTIVES_TAB", "🎯 Weekly Objectives")
ANALYTICS_TAB = os.environ.get("FR_ANALYTICS_TAB", "📈 Analytics")

if not SHEET_KEY:
    raise SystemExit(
        "FR_SHEET_KEY is not set. Copy .env.example to .env and fill in your "
        "sheet id (and FR_SERVICE_ACCOUNT if the key file isn't ./service-account.json)."
    )

# canonical skill order + how each is measured
SKILLS = ["Listening", "Grammar", "Vocab", "Reading", "Writing", "Speaking"]
UNIT = {
    "Listening": "min",
    "Grammar": "quizzes",
    "Vocab": "cards",
    "Reading": "min",
    "Writing": "prompts",
    "Speaking": "min",
}
TIME_SKILLS = [s for s, u in UNIT.items() if u == "min"]
COUNT_SKILLS = [s for s in SKILLS if s not in TIME_SKILLS]

# Rough time-equivalents so count-based skills can be compared in minutes.
# Deliberately approximate - tune these to taste.
#   vocab   : ~5 seconds per Anki card          (300 cards ~ 25 min)
#   grammar : ~5 minutes per lesson / quiz
#   writing : ~25 minutes per prompt             (drafting + reviewing)
EST_MIN_PER_UNIT = {
    "Listening": 1.0,
    "Grammar": 5.0,
    "Vocab": 5.0 / 60.0,
    "Reading": 1.0,
    "Writing": 25.0,
    "Speaking": 1.0,
}


def estimated_minutes(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-skill minute-equivalents: raw for timed skills, converted for counts."""
    return frame[SKILLS].mul(pd.Series(EST_MIN_PER_UNIT))


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _client():
    return gspread.service_account(filename=SERVICE_ACCOUNT)


def load_daily_log(gc=None) -> pd.DataFrame:
    """
    Return the Daily Log as a tidy, gap-filled daily DataFrame indexed by date.

    - Skill columns are numeric (blank -> 0.0).
    - The index is a continuous daily range from the first entry to the last
      day that actually has data (pre-seeded empty future rows are dropped).
    - Adds helper columns: `active` (any skill > 0), `active_non_grammar`
      (any skill except a lone Grammar tick), `total_minutes` (timed skills only),
      `est_minutes` (all six skills converted to minute-equivalents).
    """
    gc = gc or _client()
    sh = gc.open_by_key(SHEET_KEY)
    records = sh.worksheet(DAILY_TAB).get_all_values()

    header, *rows = records
    raw = pd.DataFrame(rows, columns=[h.split("\n")[0].strip() for h in header])

    raw["Date"] = pd.to_datetime(raw["Date"], format="%d %b %Y", errors="coerce")
    raw = raw.dropna(subset=["Date"]).set_index("Date").sort_index()

    for s in SKILLS:
        raw[s] = pd.to_numeric(
            raw[s].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )

    skills = raw[SKILLS]
    # last day with any real number recorded
    has_data = skills.notna().any(axis=1) & (skills.fillna(0).sum(axis=1) > 0)
    if not has_data.any():
        raise RuntimeError("No data rows found in Daily Log.")
    last_day = skills.index[has_data][-1]

    full = pd.date_range(skills.index.min(), last_day, freq="D")
    df = skills.reindex(full).fillna(0.0)
    df.index.name = "Date"

    df["Notes"] = raw["Notes"].reindex(full).fillna("")
    df["active"] = (df[SKILLS] > 0).any(axis=1)
    grammar_only = (df["Grammar"] > 0) & (df[[c for c in SKILLS if c != "Grammar"]] == 0).all(axis=1)
    df["active_non_grammar"] = df["active"] & ~grammar_only
    df["total_minutes"] = df[TIME_SKILLS].sum(axis=1)
    df["est_minutes"] = estimated_minutes(df).sum(axis=1)
    return df


def load_objectives(gc=None) -> pd.DataFrame:
    gc = gc or _client()
    sh = gc.open_by_key(SHEET_KEY)
    records = sh.worksheet(OBJECTIVES_TAB).get_all_values()
    header, *rows = records
    obj = pd.DataFrame(rows, columns=[h.strip() for h in header])
    obj["Week Starting"] = pd.to_datetime(obj["Week Starting"], errors="coerce")
    obj = obj.dropna(subset=["Week Starting"]).set_index("Week Starting").sort_index()
    for s in SKILLS:
        obj[s] = pd.to_numeric(obj[s], errors="coerce").fillna(0)
    # drop all-zero placeholder weeks
    obj = obj[obj[SKILLS].sum(axis=1) > 0]
    return obj[SKILLS]


# --------------------------------------------------------------------------- #
# analytics
# --------------------------------------------------------------------------- #
def _run_lengths(mask: pd.Series):
    """Yield (start_date, end_date, length) for each run of True in a daily mask."""
    runs = []
    start = None
    for day, val in mask.items():
        if val and start is None:
            start = day
        elif not val and start is not None:
            runs.append((start, prev, (prev - start).days + 1))
            start = None
        prev = day
    if start is not None:
        runs.append((start, prev, (prev - start).days + 1))
    return runs


def streaks(df: pd.DataFrame) -> dict:
    mask = df["active"]
    runs = _run_lengths(mask)
    longest = max(runs, key=lambda r: r[2]) if runs else None

    # current streak: consecutive active days ending on the last row
    current = 0
    for val in mask.values[::-1]:
        if val:
            current += 1
        else:
            break
    current_start = df.index[-current] if current else None

    gaps = _run_lengths(~mask)
    longest_gap = max(gaps, key=lambda r: r[2]) if gaps else None

    # per-skill "touched it" current streak
    per_skill_current = {}
    for s in SKILLS:
        c = 0
        for val in (df[s] > 0).values[::-1]:
            if val:
                c += 1
            else:
                break
        per_skill_current[s] = c

    return {
        "current": current,
        "current_start": current_start,
        "current_live": bool(mask.iloc[-1]),
        "longest": longest,          # (start, end, length)
        "longest_gap": longest_gap,
        "all_runs": runs,
        "per_skill_current": per_skill_current,
        "active_days": int(mask.sum()),
        "tracked_days": len(df),
        "consistency_pct": 100 * mask.mean(),
        "active_days_non_grammar": int(df["active_non_grammar"].sum()),
    }


def totals(df: pd.DataFrame) -> pd.DataFrame:
    est = estimated_minutes(df)
    out = []
    for s in SKILLS:
        col = df[s]
        days = int((col > 0).sum())
        total = col.sum()
        est_min = est[s].sum()
        out.append(
            {
                "skill": s,
                "unit": UNIT[s],
                "total": total,
                "hours": total / 60 if UNIT[s] == "min" else np.nan,
                "est_hours": est_min / 60,          # minute-equivalent hours (all skills)
                "days_practiced": days,
                "pct_of_days": 100 * days / len(df),
                "avg_per_active_day": total / days if days else 0.0,
                "avg_per_calendar_day": total / len(df),
                "best_day": col.max(),
                "best_day_date": col.idxmax().date() if col.max() > 0 else None,
            }
        )
    return pd.DataFrame(out).set_index("skill")


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Skill totals per ISO-style week starting Monday."""
    wk = df[SKILLS].resample("W-SUN").sum()
    wk.index = wk.index - pd.Timedelta(days=6)  # label by Monday (week start)
    wk.index.name = "Week Starting"
    return wk


def momentum(df: pd.DataFrame) -> pd.DataFrame:
    """Last 7 days vs the previous 7, plus the 30-day daily average."""
    last7 = df[SKILLS].iloc[-7:].sum()
    prev7 = df[SKILLS].iloc[-14:-7].sum()
    d30 = df[SKILLS].iloc[-30:].mean()
    all_daily = df[SKILLS].mean()
    m = pd.DataFrame(
        {
            "last_7d_total": last7,
            "prev_7d_total": prev7,
            "wow_change_pct": np.where(prev7 > 0, 100 * (last7 - prev7) / prev7, np.nan),
            "last_30d_avg_per_day": d30,
            "all_time_avg_per_day": all_daily,
        }
    )
    return m


def trend_slopes(df: pd.DataFrame) -> pd.DataFrame:
    """OLS slope of a 7-day rolling mean per skill => units/day drift."""
    roll = df[SKILLS].rolling(7, min_periods=3).mean().dropna()
    x = np.arange(len(roll))
    rows = {}
    for s in SKILLS:
        y = roll[s].values
        slope = np.polyfit(x, y, 1)[0] if len(x) > 1 else 0.0
        rows[s] = {
            "slope_per_day": slope,
            "slope_per_week": slope * 7,
            "first_week_avg": y[:7].mean(),
            "last_week_avg": y[-7:].mean(),
        }
    return pd.DataFrame(rows).T


def skill_balance(df: pd.DataFrame, obj: pd.DataFrame | None) -> pd.DataFrame:
    """
    Compare skills on a common footing:
      - share of estimated time (all six skills, minute-equivalents)
      - share of logged minutes (timed skills only)
      - consistency: % of tracked days the skill was touched
      - coefficient of variation of daily effort (spikiness)
      - attainment vs the average weekly objective, if objectives are available
    """
    rows = {}
    total_min = df[TIME_SKILLS].sum().sum()
    est = estimated_minutes(df)
    total_est = est.sum().sum()
    for s in SKILLS:
        col = df[s]
        active = col[col > 0]
        rows[s] = {
            "share_of_time_pct": 100 * est[s].sum() / total_est if total_est else np.nan,
            "share_of_minutes_pct": 100 * col.sum() / total_min if UNIT[s] == "min" else np.nan,
            "days_touched_pct": 100 * (col > 0).mean(),
            "cv_daily": (col.std() / col.mean()) if col.mean() else np.nan,
            "median_active_day": active.median() if len(active) else 0.0,
        }
    bal = pd.DataFrame(rows).T

    if obj is not None and len(obj):
        wk = weekly(df)
        common = wk.index.intersection(obj.index)
        if len(common):
            ratio = (wk.loc[common] / obj.loc[common].replace(0, np.nan)) * 100
            bal["obj_attainment_pct_mean"] = ratio.mean()
            bal["obj_weeks_hit_pct"] = 100 * (ratio >= 100).mean()
    return bal


def objective_attainment(df: pd.DataFrame, obj: pd.DataFrame) -> pd.DataFrame:
    wk = weekly(df)
    common = wk.index.intersection(obj.index)
    wk, obj = wk.loc[common], obj.loc[common]
    pct = (wk / obj.replace(0, np.nan)) * 100
    pct.columns = [f"{c} %" for c in pct.columns]
    return pct.round(0)


def day_of_week(df: pd.DataFrame) -> pd.DataFrame:
    dow = df.copy()
    dow["dow"] = dow.index.day_name()
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    g = dow.groupby("dow")
    out = pd.DataFrame(
        {
            "avg_total_minutes": g["total_minutes"].mean(),
            "active_rate_pct": 100 * g["active"].mean(),
            "avg_vocab": g["Vocab"].mean(),
        }
    ).reindex(order)
    return out


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_run(run):
    if not run:
        return "—"
    s, e, n = run
    return f"{n} days ({s.date():%d %b} → {e.date():%d %b})"


def build_report(df=None, obj=None) -> str:
    if df is None:
        df = load_daily_log()
    if obj is None:
        try:
            obj = load_objectives()
        except Exception:
            obj = None

    L = []
    p = L.append
    start, end = df.index[0].date(), df.index[-1].date()
    p("=" * 64)
    p(f"  FRENCH ANALYTICS  ·  {start:%d %b %Y} → {end:%d %b %Y}  ({len(df)} days)")
    p("=" * 64)

    # streaks -------------------------------------------------------------
    s = streaks(df)
    p("\n── STREAKS & CONSISTENCY ─────────────────────────────────────────")
    live = "current, live" if s["current_live"] else "ended"
    p(f"  Current streak      {s['current']} days ({live})")
    p(f"  Longest streak      {_fmt_run(s['longest'])}")
    p(f"  Longest gap         {_fmt_run(s['longest_gap'])}")
    p(f"  Active days         {s['active_days']}/{s['tracked_days']}  ({s['consistency_pct']:.0f}%)")
    p(f"  ...excl. grammar-only ticks: {s['active_days_non_grammar']} days")
    ps = "  ".join(f"{k} {v}d" for k, v in s["per_skill_current"].items())
    p(f"  Per-skill current run   {ps}")

    # totals ------------------------------------------------------------
    t = totals(df)
    p("\n── ALL-TIME TOTALS ──────────────────────────────────────────────")
    p(f"  {'skill':<10}{'total':>10}{'hours':>8}{'days':>7}{'/day*':>9}{'best day':>12}")
    for sk, r in t.iterrows():
        hrs = f"{r['hours']:.1f}" if pd.notna(r["hours"]) else "—"
        bd = f"{r['best_day']:.0f} {r['best_day_date']:%d %b}" if r["best_day_date"] else "—"
        p(f"  {sk:<10}{r['total']:>10,.0f}{hrs:>8}{r['days_practiced']:>7}"
          f"{r['avg_per_active_day']:>9.1f}{bd:>12}")
    p("  * per active day for that skill")
    tot_hours = t["hours"].dropna().sum()
    p(f"  Total logged time (listening+reading+speaking): {tot_hours:.1f} hrs")

    # estimated time on french --------------------------------------
    p("\n── ESTIMATED TIME ON FRENCH  (count skills -> minutes) ───────────")
    p(f"  assumptions: vocab {EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card, "
      f"grammar {EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson, "
      f"writing {EST_MIN_PER_UNIT['Writing']:.0f}min/prompt")
    for sk, r in t.iterrows():
        bar = "█" * round(r["est_hours"] / max(t["est_hours"]) * 24)
        p(f"  {sk:<10}{r['est_hours']:>7.1f} h  {bar}")
    p(f"  {'TOTAL':<10}{t['est_hours'].sum():>7.1f} h   (vs {tot_hours:.1f} h logged directly)")

    # momentum --------------------------------------------------------
    m = momentum(df)
    p("\n── MOMENTUM  (last 7 days vs previous 7) ─────────────────────────")
    p(f"  {'skill':<10}{'last 7d':>10}{'prev 7d':>10}{'WoW':>9}{'30d/day':>10}")
    for sk, r in m.iterrows():
        wow = f"{r['wow_change_pct']:+.0f}%" if pd.notna(r["wow_change_pct"]) else "—"
        p(f"  {sk:<10}{r['last_7d_total']:>10,.0f}{r['prev_7d_total']:>10,.0f}"
          f"{wow:>9}{r['last_30d_avg_per_day']:>10.1f}")

    # trends --------------------------------------------------------
    tr = trend_slopes(df)
    p("\n── TREND  (7-day rolling mean, first week → last week) ───────────")
    for sk, r in tr.iterrows():
        arrow = "↑" if r["slope_per_week"] > 0 else "↓" if r["slope_per_week"] < 0 else "→"
        p(f"  {sk:<10}{r['first_week_avg']:>8.1f} → {r['last_week_avg']:>6.1f} /day"
          f"   {arrow} {r['slope_per_week']:+.2f}/day per week")

    # skill balance -------------------------------------------------
    bal = skill_balance(df, obj)
    p("\n── SKILL BALANCE ────────────────────────────────────────────────")
    cols = ["share_of_time_pct", "days_touched_pct", "cv_daily", "median_active_day"]
    if "obj_attainment_pct_mean" in bal:
        cols += ["obj_attainment_pct_mean", "obj_weeks_hit_pct"]
    hdr = {"share_of_time_pct": "time share", "share_of_minutes_pct": "min share",
           "days_touched_pct": "days %",
           "cv_daily": "spikiness", "median_active_day": "med/day",
           "obj_attainment_pct_mean": "obj att%", "obj_weeks_hit_pct": "wks hit%"}
    p("  " + f"{'skill':<10}" + "".join(f"{hdr[c]:>11}" for c in cols))
    for sk, r in bal.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if pd.isna(v):
                cells.append(f"{'—':>11}")
            elif c == "cv_daily":
                cells.append(f"{v:>11.2f}")
            elif c == "median_active_day":
                cells.append(f"{v:>11.0f}")
            else:
                cells.append(f"{v:>10.0f}%")
        p(f"  {sk:<10}" + "".join(cells))
    # neglect callout
    touched = bal["days_touched_pct"].sort_values()
    p(f"  Most neglected: {touched.index[0]} ({touched.iloc[0]:.0f}% of days)"
      f"  ·  Most consistent: {touched.index[-1]} ({touched.iloc[-1]:.0f}%)")

    # objectives --------------------------------------------------
    if obj is not None and len(obj):
        oa = objective_attainment(df, obj)
        p("\n── WEEKLY OBJECTIVE ATTAINMENT  (% of target) ───────────────────")
        p("  " + f"{'week':<12}" + "".join(f"{c.split()[0][:4]:>7}" for c in oa.columns))
        for wkstart, r in oa.iterrows():
            p(f"  {wkstart.date():%d %b %y}".ljust(14)
              + "".join(f"{('—' if pd.isna(v) else f'{v:.0f}'):>7}" for v in r.values))
        hit = (oa >= 100).mean() * 100
        p("  weeks ≥100%: " + "  ".join(f"{c.split()[0]} {hit[c]:.0f}%" for c in oa.columns))

    # day of week ----------------------------------------------
    dw = day_of_week(df)
    p("\n── DAY-OF-WEEK PATTERN ──────────────────────────────────────────")
    p(f"  {'day':<11}{'avg min':>9}{'active %':>10}{'avg vocab':>11}")
    for d, r in dw.iterrows():
        p(f"  {d:<11}{r['avg_total_minutes']:>9.0f}{r['active_rate_pct']:>9.0f}%{r['avg_vocab']:>11.0f}")
    best = dw["avg_total_minutes"].idxmax()
    worst = dw["avg_total_minutes"].idxmin()
    p(f"  Strongest: {best}   ·   Weakest: {worst}")

    p("\n" + "=" * 64)
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# optional: push a compact summary into the Analytics tab
# --------------------------------------------------------------------------- #
def push_to_sheet(df=None, obj=None, start_cell="A20"):
    gc = _client()
    if df is None:
        df = load_daily_log(gc)
    if obj is None:
        try:
            obj = load_objectives(gc)
        except Exception:
            obj = None
    sh = gc.open_by_key(SHEET_KEY)
    ws = sh.worksheet(ANALYTICS_TAB)

    s = streaks(df)
    t = totals(df)
    m = momentum(df)
    bal = skill_balance(df, obj)
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    block = [
        [f"🔁 Streaks & Momentum  (auto-generated {stamp})"],
        ["Current streak (days)", s["current"], "live" if s["current_live"] else "ended"],
        ["Longest streak (days)", s["longest"][2] if s["longest"] else 0],
        ["Longest gap (days)", s["longest_gap"][2] if s["longest_gap"] else 0],
        ["Active days", f'{s["active_days"]}/{s["tracked_days"]}', f'{s["consistency_pct"]:.0f}%'],
        ["Estimated total time (hrs)", round(float(t["est_hours"].sum()), 1),
         f'{round(float(t["hours"].dropna().sum()), 1)} logged directly'],
        [],
        ["Skill", "Total", "Logged hrs", "Est. hrs", "Days", "Avg/active day",
         "Last 7d", "Prev 7d", "Days touched %"],
    ]
    for sk in SKILLS:
        r, mr = t.loc[sk], m.loc[sk]
        block.append([
            sk,
            round(float(r["total"])),
            round(float(r["hours"]), 1) if pd.notna(r["hours"]) else "—",
            round(float(r["est_hours"]), 1),
            int(r["days_practiced"]),
            round(float(r["avg_per_active_day"]), 1),
            round(float(mr["last_7d_total"])),
            round(float(mr["prev_7d_total"])),
            round(float(bal.loc[sk, "days_touched_pct"])),
        ])
    block += [
        [],
        ["Most neglected", bal["days_touched_pct"].idxmin()],
        ["Most consistent", bal["days_touched_pct"].idxmax()],
        ["Est-time assumptions",
         f"vocab {EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card, grammar "
         f"{EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson, writing "
         f"{EST_MIN_PER_UNIT['Writing']:.0f}min/prompt"],
    ]
    # clear a generous window first so a shorter block never leaves stale rows
    col = start_cell.rstrip("0123456789") or "A"
    row0 = int(start_cell[len(col):] or 1)
    ws.batch_clear([f"{col}{row0}:Z{row0 + max(len(block) + 20, 60)}"])
    ws.update(block, start_cell, value_input_option="USER_ENTERED")
    print(f"Wrote {len(block)} rows to '{ANALYTICS_TAB}' starting at {start_cell}")


if __name__ == "__main__":
    _df = load_daily_log()
    _obj = None
    try:
        _obj = load_objectives()
    except Exception as e:  # noqa
        print(f"(objectives unavailable: {e})")
    print(build_report(_df, _obj))
    if "--push" in sys.argv:
        push_to_sheet(_df, _obj)
