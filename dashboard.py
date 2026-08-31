"""
French habit tracker - visual dashboard.

Pulls fresh data through analytics.py and renders a single self-contained
`dashboard.html` (inline CSS + hand-built SVG, no external requests), then opens
it in your browser.

    python dashboard.py                # build dashboard.html and open it
    python dashboard.py --no-open      # just build the file
    python dashboard.py --out foo.html # write somewhere else

Re-run it whenever you want the latest picture - it always reflects the sheet.
"""

from __future__ import annotations

import os
import sys
import html
import datetime as dt
import webbrowser
from pathlib import Path

import numpy as np
import pandas as pd

import analytics as A

SKILLS = A.SKILLS
UNIT = A.UNIT
TIME_SKILLS = A.TIME_SKILLS


# --------------------------------------------------------------------------- #
# tiny svg helpers
# --------------------------------------------------------------------------- #
def esc(x) -> str:
    return html.escape(str(x), quote=True)


def fmt(n, nd=0) -> str:
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return "-"
    if nd == 0:
        return f"{round(n):,}"
    return f"{n:,.{nd}f}"


# --------------------------------------------------------------------------- #
# 1. study calendar heatmap (sequential blue, one <svg>)
# --------------------------------------------------------------------------- #
def heatmap_svg(df: pd.DataFrame) -> str:
    pitch, cell = 15, 13
    first = df.index[0]
    first_monday = first - pd.Timedelta(days=first.weekday())
    n_weeks = ((df.index[-1] - first_monday).days // 7) + 1

    pad_l, pad_t = 34, 32
    w = pad_l + n_weeks * pitch + 8
    h = pad_t + 7 * pitch + 30

    def bucket(m: float) -> int:
        """colour level 0-4 by estimated minutes of study that day."""
        if m <= 0:
            return 0
        for lvl, hi in ((1, 20), (2, 45), (3, 90)):
            if m <= hi:
                return lvl
        return 4

    cells = []
    months = []
    seen_month = set()
    for day, row in df.iterrows():
        wk = (day - first_monday).days // 7
        x = pad_l + wk * pitch
        y = pad_t + day.weekday() * pitch
        lvl = bucket(row["est_minutes"])
        parts = [f"{s} {fmt(row[s])} {UNIT[s]}" for s in SKILLS if row[s] > 0]
        emin = row["est_minutes"]
        detail = f"~{emin:.0f} min · " + ", ".join(parts) if parts else "rest day"
        tip = f"{day:%a %d %b %Y} - {detail}"
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" '
            f'fill="var(--heat-{lvl})"><title>{esc(tip)}</title></rect>'
        )
        mkey = (day.year, day.month)
        if day.day <= 7 and mkey not in seen_month:
            seen_month.add(mkey)
            months.append(f'<text class="hm-mon" x="{x}" y="{pad_t-9}">{day:%b}</text>')

    dow_lbl = "".join(
        f'<text class="hm-dow" x="{pad_l-8}" y="{pad_t + i*pitch + cell-3}">{d}</text>'
        for i, d in [(0, "M"), (2, "W"), (4, "F"), (6, "S")]
    )

    # legend
    lx, ly = pad_l, h - 14
    legend = [f'<text class="hm-dow" x="{lx-6}" y="{ly+10}">less</text>']
    for i in range(5):
        legend.append(
            f'<rect x="{lx + 20 + i*pitch}" y="{ly}" width="{cell}" height="{cell}" rx="3" '
            f'fill="var(--heat-{i})"/>'
        )
    legend.append(
        f'<text class="hm-dow" style="text-anchor:start" '
        f'x="{lx + 20 + 5*pitch + 6}" y="{ly+10}">more</text>'
    )

    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="Daily study calendar shaded by estimated minutes of study">'
        f'{"".join(months)}{dow_lbl}{"".join(cells)}{"".join(legend)}</svg>'
    )


# --------------------------------------------------------------------------- #
# 2. 7-day rolling average, small multiples (one <svg> per skill, all blue)
# --------------------------------------------------------------------------- #
def _panel(title: str, sub: str, series: np.ndarray, unit: str,
           target: float | None = None) -> str:
    W, H = 340, 132
    ml, mr, mt, mb = 10, 10, 30, 16
    n = len(series)
    ymax = max(series.max(), (target or 0)) * 1.15 or 1
    xs = lambda i: ml + (W - ml - mr) * (i / (n - 1) if n > 1 else 0)
    ys = lambda v: H - mb - (H - mt - mb) * (v / ymax)

    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(series))
    area = f"{ml},{ys(0):.1f} " + pts + f" {xs(n-1):.1f},{ys(0):.1f}"
    end_x, end_y = xs(n - 1), ys(series[-1])

    tline = ""
    if target:
        ty = ys(target)
        tline = (
            f'<line class="p-target" x1="{ml}" y1="{ty:.1f}" x2="{W-mr}" y2="{ty:.1f}"/>'
            f'<text class="p-tlabel" x="{W-mr}" y="{ty-4:.1f}">target {fmt(target)}</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{esc(title)} {esc(sub)}">'
        f'<text class="p-title" x="{ml}" y="13">{esc(title)}</text>'
        f'<text class="p-sub" x="{ml}" y="25">{esc(sub)}</text>'
        f'<polygon class="p-area" points="{area}"/>'
        f'<polyline class="p-line" points="{pts}"/>'
        f'{tline}'
        f'<circle class="p-end" cx="{end_x:.1f}" cy="{end_y:.1f}" r="3.5"/>'
        f'<text class="p-endlab" x="{end_x-6:.1f}" y="{end_y-7:.1f}">{fmt(series[-1],1)}</text>'
        f"</svg>"
    )


def trend_panels(df: pd.DataFrame) -> str:
    roll = df[SKILLS].rolling(7, min_periods=3).mean().bfill()
    tr = A.trend_slopes(df)
    out = []
    for s in SKILLS:
        r = tr.loc[s]
        arrow = "↗" if r["slope_per_week"] > 0.05 else "↘" if r["slope_per_week"] < -0.05 else "→"
        sub = f'{fmt(r["first_week_avg"],1)} {arrow} {fmt(r["last_week_avg"],1)} {UNIT[s]}/day'
        out.append(_panel(s, sub, roll[s].to_numpy(), UNIT[s]))
    return f'<div class="grid">{"".join(out)}</div>'


# --------------------------------------------------------------------------- #
# 3. weekly totals vs objective, small multiples
# --------------------------------------------------------------------------- #
def weekly_panels(df: pd.DataFrame, obj: pd.DataFrame | None) -> str:
    wk = A.weekly(df)
    common = wk.index if obj is None else wk.index.intersection(obj.index)
    wk = wk.loc[common]
    out = []
    for s in SKILLS:
        vals = wk[s].to_numpy(dtype=float)
        tgt = None
        hit_txt = ""
        if obj is not None and s in obj:
            tg = obj.loc[common, s].replace(0, np.nan)
            tgt = float(np.nanmedian(tg)) if tg.notna().any() else None
            if tg.notna().any():
                hit = float((wk[s] >= tg).mean() * 100)
                hit_txt = f"  -  {hit:.0f}% of weeks on target"
        out.append(_bars_panel(s, f"weekly {UNIT[s]}{hit_txt}", vals, tgt))
    return f'<div class="grid">{"".join(out)}</div>'


def _bars_panel(title: str, sub: str, vals: np.ndarray, target: float | None) -> str:
    W, H = 340, 132
    ml, mr, mt, mb = 10, 10, 30, 14
    n = len(vals)
    ymax = max(vals.max(), (target or 0)) * 1.15 or 1
    slot = (W - ml - mr) / n
    bw = min(18, slot - 3)
    y0 = H - mb
    ys = lambda v: y0 - (H - mt - mb) * (v / ymax)

    bars = []
    for i, v in enumerate(vals):
        x = ml + i * slot + (slot - bw) / 2
        yv = ys(v)
        bars.append(
            f'<rect class="b-bar" x="{x:.1f}" y="{yv:.1f}" width="{bw:.1f}" '
            f'height="{max(0, y0-yv):.1f}" rx="3"><title>{fmt(v)}</title></rect>'
        )
    tline = ""
    if target:
        ty = ys(target)
        tline = (f'<line class="p-target" x1="{ml}" y1="{ty:.1f}" x2="{W-mr}" y2="{ty:.1f}"/>'
                 f'<text class="p-tlabel" x="{W-mr}" y="{ty-4:.1f}">target {fmt(target)}</text>')
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{esc(title)} {esc(sub)}">'
        f'<text class="p-title" x="{ml}" y="13">{esc(title)}</text>'
        f'<text class="p-sub" x="{ml}" y="25">{esc(sub)}</text>'
        f'<line class="p-base" x1="{ml}" y1="{y0}" x2="{W-mr}" y2="{y0}"/>'
        f'{"".join(bars)}{tline}</svg>'
    )


# --------------------------------------------------------------------------- #
# 4. skill balance - horizontal bars, % of days touched
# --------------------------------------------------------------------------- #
def balance_svg(df: pd.DataFrame, obj: pd.DataFrame | None) -> str:
    bal = A.skill_balance(df, obj).sort_values("days_touched_pct", ascending=True)
    rows = list(bal.index)
    W = 560
    rowh = 34
    H = rowh * len(rows) + 20
    ml, mr = 96, 60
    span = W - ml - mr
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Share of days each skill was practised">']
    for i, s in enumerate(rows):
        y = 14 + i * rowh
        pct = bal.loc[s, "days_touched_pct"]
        bw = span * pct / 100
        out.append(f'<text class="h-cat" x="{ml-10}" y="{y+13}">{esc(s)}</text>')
        out.append(f'<rect class="h-track" x="{ml}" y="{y}" width="{span}" height="18" rx="4"/>')
        out.append(f'<rect class="h-fill" x="{ml}" y="{y}" width="{bw:.1f}" height="18" rx="4">'
                   f'<title>{esc(s)}: practised on {pct:.0f}% of days</title></rect>')
        out.append(f'<text class="h-val" x="{ml+bw+6:.1f}" y="{y+13}">{pct:.0f}%</text>')
        oa = bal.loc[s].get("obj_attainment_pct_mean", np.nan)
        if not np.isnan(oa):
            ox = ml + span * min(oa, 100) / 100
            out.append(f'<line class="h-obj" x1="{ox:.1f}" y1="{y-3}" x2="{ox:.1f}" y2="{y+21}">'
                       f'<title>avg {oa:.0f}% of weekly objective</title></line>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# 5. where the time goes - stacked bar of estimated minutes, all six skills
# --------------------------------------------------------------------------- #
SLOT = {  # hue per skill, ordered so lookalike pastels never sit side by side
    "Listening": "--series-1",  # blue
    "Grammar": "--series-4",    # gold
    "Vocab": "--series-6",      # teal
    "Reading": "--series-2",    # rose
    "Writing": "--series-5",    # purple
    "Speaking": "--series-3",   # green
}


def timesplit_svg(df: pd.DataFrame) -> str:
    est = A.estimated_minutes(df).sum()          # minutes per skill
    total = float(est.sum()) or 1.0
    W, H = 560, 96

    x = 0.0
    segs = []
    for s in SKILLS:
        frac = est[s] / total
        wpx = (W - 4) * frac
        segs.append(
            f'<rect x="{x:.1f}" y="0" width="{max(0, wpx-2):.1f}" height="24" rx="3" '
            f'fill="var({SLOT[s]})"><title>{esc(s)}: {est[s]/60:.1f} h '
            f'({frac*100:.0f}%)</title></rect>'
        )
        x += wpx

    # legend: two rows of three, so nothing collides on the thin segments
    leg = []
    for i, s in enumerate(SKILLS):
        col, rown = i % 3, i // 3
        lx, ly = col * (W / 3), 40 + rown * 26
        frac = est[s] / total
        leg.append(
            f'<rect x="{lx:.1f}" y="{ly}" width="10" height="10" rx="2" fill="var({SLOT[s]})"/>'
            f'<text class="ts-lab" x="{lx+15:.1f}" y="{ly+9:.0f}">{esc(s)}</text>'
            f'<text class="ts-val" x="{lx+15:.1f}" y="{ly+22:.0f}">'
            f'{frac*100:.0f}% · {est[s]/60:.1f} h</text>'
        )
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
            f'aria-label="Share of estimated study time across all six skills">'
            f'{"".join(segs)}{"".join(leg)}</svg>')


# --------------------------------------------------------------------------- #
# 6. day-of-week columns
# --------------------------------------------------------------------------- #
def dow_svg(df: pd.DataFrame) -> str:
    dw = A.day_of_week(df)
    W, H = 560, 176
    ml, mr, mt, mb = 8, 8, 26, 24
    order = list(dw.index)
    vals = dw["avg_total_minutes"].to_numpy()
    ymax = vals.max() * 1.2 or 1
    slot = (W - ml - mr) / len(order)
    bw = min(30, slot - 12)
    y0 = H - mb
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Average minutes practised by day of week">']
    out.append(f'<line class="p-base" x1="{ml}" y1="{y0}" x2="{W-mr}" y2="{y0}"/>')
    for i, d in enumerate(order):
        v = vals[i]
        x = ml + i * slot + (slot - bw) / 2
        yv = y0 - (H - mt - mb) * (v / ymax)
        out.append(f'<rect class="b-bar" x="{x:.1f}" y="{yv:.1f}" width="{bw:.1f}" '
                   f'height="{y0-yv:.1f}" rx="3"><title>{d}: {v:.0f} min/day avg</title></rect>')
        out.append(f'<text class="d-lab" x="{x+bw/2:.1f}" y="{y0+15}">{d[:3]}</text>')
        out.append(f'<text class="d-val" x="{x+bw/2:.1f}" y="{yv-6:.1f}">{v:.0f}</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# 7. combined 6-panel grids (one <svg>) - used for the README, where each
#    chart has to be a single embeddable image
# --------------------------------------------------------------------------- #
_PW, _PH, _PGAP = 250, 118, 14          # panel box + gap
_PCOLS = 3


def _grid_shell(n: int, label: str):
    rows = (n + _PCOLS - 1) // _PCOLS
    w = _PCOLS * _PW + (_PCOLS - 1) * _PGAP
    h = rows * _PH + (rows - 1) * _PGAP
    head = (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
            f'aria-label="{esc(label)}">')
    def origin(i):
        return (i % _PCOLS) * (_PW + _PGAP), (i // _PCOLS) * (_PH + _PGAP)
    return head, origin, w, h


def _line_panel(ox, oy, title, sub, series, target=None):
    ml, mr, mt, mb = 6, 6, 30, 12
    n = len(series)
    ymax = (max(float(series.max()), target or 0) * 1.15) or 1
    xs = lambda i: ox + ml + (_PW - ml - mr) * (i / (n - 1) if n > 1 else 0)
    ys = lambda v: oy + _PH - mb - (_PH - mt - mb) * (v / ymax)
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(series))
    area = f"{ox+ml},{ys(0):.1f} {pts} {xs(n-1):.1f},{ys(0):.1f}"
    ex, ey = xs(n - 1), ys(series[-1])
    return (
        f'<text class="p-title" x="{ox+ml}" y="{oy+13}">{esc(title)}</text>'
        f'<text class="p-sub" x="{ox+ml}" y="{oy+25}">{esc(sub)}</text>'
        f'<polygon class="p-area" points="{area}"/>'
        f'<polyline class="p-line" points="{pts}"/>'
        f'<circle class="p-end" cx="{ex:.1f}" cy="{ey:.1f}" r="3"/>'
    )


def _col_panel(ox, oy, title, sub, vals, target=None):
    ml, mr, mt, mb = 6, 6, 30, 12
    n = len(vals)
    ymax = (max(float(vals.max()), target or 0) * 1.15) or 1
    slot = (_PW - ml - mr) / n
    bw = min(14, slot - 2)
    y0 = oy + _PH - mb
    ys = lambda v: y0 - (_PH - mt - mb) * (v / ymax)
    bars = "".join(
        f'<rect class="b-bar" x="{ox+ml+i*slot+(slot-bw)/2:.1f}" y="{ys(v):.1f}" '
        f'width="{bw:.1f}" height="{max(0, y0-ys(v)):.1f}" rx="2"/>'
        for i, v in enumerate(vals)
    )
    tline = ""
    if target:
        ty = ys(target)
        tline = (f'<line class="p-target" x1="{ox+ml}" y1="{ty:.1f}" '
                 f'x2="{ox+_PW-mr}" y2="{ty:.1f}"/>')
    return (
        f'<text class="p-title" x="{ox+ml}" y="{oy+13}">{esc(title)}</text>'
        f'<text class="p-sub" x="{ox+ml}" y="{oy+25}">{esc(sub)}</text>'
        f'<line class="p-base" x1="{ox+ml}" y1="{y0}" x2="{ox+_PW-mr}" y2="{y0}"/>'
        f'{bars}{tline}'
    )


def trend_grid_svg(df: pd.DataFrame) -> str:
    roll = df[SKILLS].rolling(7, min_periods=3).mean().bfill()
    tr = A.trend_slopes(df)
    head, origin, *_ = _grid_shell(len(SKILLS), "7-day rolling average per skill")
    body = []
    for i, s in enumerate(SKILLS):
        r = tr.loc[s]
        arrow = "up" if r["slope_per_week"] > 0.05 else "down" if r["slope_per_week"] < -0.05 else "flat"
        sub = f'{fmt(r["first_week_avg"],1)} -> {fmt(r["last_week_avg"],1)} {UNIT[s]}/day ({arrow})'
        ox, oy = origin(i)
        body.append(_line_panel(ox, oy, s, sub, roll[s].to_numpy()))
    return head + "".join(body) + "</svg>"


def objective_grid_svg(df: pd.DataFrame, obj: "pd.DataFrame | None") -> str:
    wk = A.weekly(df)
    common = wk.index if obj is None else wk.index.intersection(obj.index)
    wk = wk.loc[common]
    head, origin, *_ = _grid_shell(len(SKILLS), "Weekly totals against objective")
    body = []
    for i, s in enumerate(SKILLS):
        vals = wk[s].to_numpy(dtype=float)
        tgt = None
        sub = f"weekly {UNIT[s]}"
        if obj is not None and s in obj:
            tg = obj.loc[common, s].replace(0, np.nan)
            if tg.notna().any():
                tgt = float(np.nanmedian(tg))
                hit = float((wk[s] >= tg).mean() * 100)
                sub = f"weekly {UNIT[s]} · {hit:.0f}% of weeks on target"
        ox, oy = origin(i)
        body.append(_col_panel(ox, oy, s, sub, vals, tgt))
    return head + "".join(body) + "</svg>"


# --------------------------------------------------------------------------- #
# assemble page
# --------------------------------------------------------------------------- #
# Muted / pastel palette. Soft on purpose - the categorical hues sit below the
# usual saturation bar, so every multi-colour chart (only the time-split bar)
# carries a legend + direct labels; the rest are single-series or the heat ramp.
_TOK_LIGHT = (
    "--plane:#faf9f6;--surface:#ffffff;--ink:#2c2c2c;--ink2:#606060;--muted:#9b9b9b;"
    "--grid:#eae7e1;--base:#d1cdc6;--border:rgba(20,20,20,.10);"
    "--series-1:#5a8fbf;--series-2:#cf8686;--series-3:#5faa82;"
    "--series-4:#c99a4a;--series-5:#927fbc;--series-6:#4ea3a3;"
    "--accent:#5a8fbf;--good:#5a8fbf;"
    "--heat-0:#edeae4;--heat-1:#d8e5f0;--heat-2:#aecbe4;--heat-3:#7ea9cd;--heat-4:#4f7ba6;"
)
_TOK_DARK = (
    "--plane:#14151a;--surface:#1d1f24;--ink:#e9e9e9;--ink2:#b2b2b2;--muted:#858585;"
    "--grid:#2b2d33;--base:#3a3d43;--border:rgba(255,255,255,.10);"
    "--series-1:#7aa6cf;--series-2:#dc9d9d;--series-3:#7cc09a;"
    "--series-4:#d6b46a;--series-5:#a998d0;--series-6:#6bb8b8;"
    "--accent:#7aa6cf;--good:#7aa6cf;"
    "--heat-0:#23252b;--heat-1:#2b4257;--heat-2:#3d6688;--heat-3:#5f92b6;--heat-4:#9ac2e0;"
)

# rules that style the hand-built SVG marks - shared by the page and by the
# standalone SVG files exported for the README.
CHART_CSS = """
.p-title{fill:var(--ink);font-size:12px;font-weight:600}
.p-sub{fill:var(--muted);font-size:10px}
.p-line{fill:none;stroke:var(--series-1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.p-area{fill:var(--series-1);opacity:.10}
.p-end{fill:var(--series-1);stroke:var(--surface);stroke-width:2}
.p-endlab{fill:var(--ink2);font-size:10px;text-anchor:end;font-weight:600}
.p-target{stroke:var(--muted);stroke-width:1;stroke-dasharray:0}
.p-tlabel{fill:var(--muted);font-size:9px;text-anchor:end}
.p-base{stroke:var(--base);stroke-width:1}
.b-bar{fill:var(--series-1)}
.b-bar:hover{fill:var(--accent);opacity:.85}
.b-hi{fill:var(--series-1)}
.d-lab{fill:var(--muted);font-size:10px;text-anchor:middle}
.d-val{fill:var(--ink2);font-size:10px;text-anchor:middle;font-weight:600}
/* heatmap */
.hm-mon{fill:var(--muted);font-size:10px}
.hm-dow{fill:var(--muted);font-size:9px;text-anchor:end}
rect:hover{opacity:.8}
/* horizontal bars */
.h-cat{fill:var(--ink);font-size:12px;text-anchor:end;dominant-baseline:middle}
.h-track{fill:var(--grid)}
.h-fill{fill:var(--accent)}
.h-val{fill:var(--ink2);font-size:11px;font-weight:600;dominant-baseline:middle}
.h-obj{stroke:var(--ink);stroke-width:2}
.ts-lab{fill:var(--ink);font-size:11px;font-weight:600}
.ts-val{fill:var(--ink2);font-size:11px}
"""

# page chrome - layout only, not used by the standalone SVGs
_LAYOUT_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;line-height:1.5;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1060px;margin:0 auto;padding:56px 24px 80px}
header{border-bottom:1px solid var(--border);padding-bottom:20px;margin-bottom:8px}
header h1{font-size:22px;margin:0 0 6px;letter-spacing:-.01em;font-weight:600}
header p{margin:0;color:var(--muted);font-size:13px}
header a{color:var(--ink2);text-decoration:none;border-bottom:1px solid var(--border)}
section{margin-top:44px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);
  margin:0 0 14px;font-weight:600}
.cap{font-size:11px;color:var(--muted);margin:10px 0 0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:20px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 18px}
.tile .lab{font-size:12px;color:var(--ink2);margin-bottom:6px}
.tile .val{font-size:30px;font-weight:600;letter-spacing:-.02em}
.tile .sub{font-size:12px;color:var(--muted);margin-top:2px}
.tile.hero .val{font-size:44px;color:var(--accent)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}
.grid svg{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:6px}
.b-bar:hover{fill:var(--accent);opacity:.85}
rect:hover{opacity:.8}
.mom{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.mom .m{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px}
.mom .sk{font-size:12px;color:var(--ink2)}
.mom .big{font-size:20px;font-weight:600;margin-top:4px}
.mom .cmp{font-size:11px;color:var(--muted);margin-top:2px}
.up{color:var(--good)} .down{color:var(--ink2)}
details{margin-top:32px;font-size:13px;color:var(--ink2)}
summary{cursor:pointer;color:var(--accent);font-weight:600}
table{border-collapse:collapse;width:100%;margin-top:12px;font-size:12px;
  font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:6px 10px;border-bottom:1px solid var(--border)}
th:first-child,td:first-child{text-align:left}
.foot{margin-top:48px;font-size:12px;color:var(--muted);text-align:center}
.foot a{color:var(--muted)}
"""

CSS = (
    f":root{{color-scheme:light;{_TOK_LIGHT}}}"
    f'@media (prefers-color-scheme:dark){{:root:not([data-theme="light"])'
    f"{{color-scheme:dark;{_TOK_DARK}}}}}"
    f':root[data-theme="dark"]{{color-scheme:dark;{_TOK_DARK}}}'
    f"{_LAYOUT_CSS}{CHART_CSS}"
)


def _token_map(tokens: str) -> dict[str, str]:
    out = {}
    for decl in tokens.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def standalone_svg(body: str, theme: str = "light") -> str:
    """Turn one of the var()/class-based chart strings into a self-contained
    .svg file: every colour resolved to a concrete hex for `theme`, xmlns added,
    the mark styles inlined. No CSS variables remain, so it renders anywhere
    (GitHub README, an <img> tag, Slack)."""
    import re

    pal = _token_map(_TOK_LIGHT if theme == "light" else _TOK_DARK)
    sub = lambda text: re.sub(r"var\((--[\w-]+)\)", lambda m: pal.get(m.group(1), m.group(0)), text)
    # a surface-coloured backdrop so the file is readable on any page, not just
    # the matching GitHub theme
    bg = f'<rect x="0" y="0" width="100%" height="100%" fill="{pal["--surface"]}"/>'
    style = f"<style>{sub(CHART_CSS)}</style>"
    body = sub(body).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    cut = body.index(">") + 1
    return body[:cut] + style + bg + body[cut:]


def export_assets(df: pd.DataFrame, obj: "pd.DataFrame | None", outdir="assets") -> list[Path]:
    """Write light+dark standalone SVGs used by the README."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    charts = {
        "calendar": heatmap_svg(df),
        "skills": balance_svg(df, obj),
        "time-split": timesplit_svg(df),
        "weekday": dow_svg(df),
        "trend": trend_grid_svg(df),
        "objectives": objective_grid_svg(df, obj),
    }
    written = []
    for name, svg in charts.items():
        for theme in ("light", "dark"):
            p = out / f"{name}-{theme}.svg"
            p.write_text(standalone_svg(svg, theme), encoding="utf-8")
            written.append(p)
    return written


def momentum_block(df: pd.DataFrame) -> str:
    m = A.momentum(df)
    cards = []
    for s in SKILLS:
        r = m.loc[s]
        wow = r["wow_change_pct"]
        last, prev = r["last_7d_total"], r["prev_7d_total"]
        if np.isnan(wow):
            if last == 0 and prev == 0:
                txt = "no activity in 14 days"
            elif prev == 0:
                txt = "up from zero last week"
            else:
                txt = "flat vs prior 7d"
            tag = f'<span class="cmp">{txt}</span>'
        else:
            up = wow >= 0
            arrow = "▲" if up else "▼"
            tag = (f'<span class="cmp {"up" if up else "down"}">{arrow} {wow:+.0f}% vs prior 7d</span>')
        cards.append(
            f'<div class="m"><div class="sk">{esc(s)}</div>'
            f'<div class="big">{fmt(r["last_7d_total"])} <span class="cmp">{UNIT[s]} / 7d</span></div>'
            f'{tag}</div>'
        )
    return f'<div class="mom">{"".join(cards)}</div>'


def weekly_table(df: pd.DataFrame, obj: pd.DataFrame | None) -> str:
    wk = A.weekly(df)
    head = "".join(f"<th>{s}</th>" for s in SKILLS)
    body = []
    for wkstart, row in wk.iterrows():
        tds = "".join(f"<td>{fmt(row[s])}</td>" for s in SKILLS)
        body.append(f"<tr><td>{wkstart:%d %b %Y}</td>{tds}</tr>")
    return f"<table><thead><tr><th>Week starting</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def page_body(df: pd.DataFrame, obj: pd.DataFrame | None) -> str:
    """The <title> + <style> + content, with no document skeleton.

    Usable as-is for a Claude Artifact (which supplies <!doctype>/<head>/<body>);
    build_html() wraps this in a standalone document for local viewing."""
    s = A.streaks(df)
    t = A.totals(df)
    start, end = df.index[0].date(), df.index[-1].date()
    total_hours = t["hours"].dropna().sum()
    est_hours = t["est_hours"].sum()
    longest = s["longest"][2] if s["longest"] else 0
    week_est_min = float(A.estimated_minutes(df).iloc[-7:].sum().sum())

    tiles = [
        ("hero", "Current streak", f'{s["current"]}', "days" + ("" if s["current_live"] else " · ended")),
        ("", "Longest streak", f"{longest}", "days"),
        ("", "Consistency", f'{s["consistency_pct"]:.0f}%', f'{s["active_days"]} of {s["tracked_days"]} days'),
        ("", "Total time", f"{est_hours:.0f}h", f"{total_hours:.0f}h logged · rest estimated"),
        ("", "Last 7 days", f"{week_est_min/60:.1f}h", "estimated"),
    ]
    tile_html = "".join(
        f'<div class="tile {c}"><div class="lab">{esc(l)}</div>'
        f'<div class="val">{esc(v)}</div><div class="sub">{esc(sub)}</div></div>'
        for c, l, v, sub in tiles
    )

    # totals table
    trows = []
    for sk, r in t.iterrows():
        hrs = f'{r["hours"]:.1f} h' if pd.notna(r["hours"]) else "—"
        trows.append(
            f"<tr><td>{sk}</td><td>{fmt(r['total'])} {UNIT[sk]}</td><td>{hrs}</td>"
            f"<td>{r['est_hours']:.1f} h</td>"
            f"<td>{int(r['days_practiced'])}</td><td>{fmt(r['avg_per_active_day'],1)}</td>"
            f"<td>{fmt(r['best_day'])} ({r['best_day_date']:%d %b})</td></tr>"
        )
    trows.append(
        f"<tr><td><strong>Total</strong></td><td></td><td>{total_hours:.1f} h</td>"
        f"<td><strong>{est_hours:.1f} h</strong></td><td></td><td></td><td></td></tr>"
    )
    totals_table = (
        "<table><thead><tr><th>Skill</th><th>Total</th><th>Logged hrs</th><th>Est. hrs</th>"
        "<th>Days</th><th>Avg / active day</th><th>Best day</th></tr></thead><tbody>"
        + "".join(trows) + "</tbody></table>"
    )

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    repo = os.environ.get("REPO_URL", "").rstrip("/")
    foot_src = f' · <a href="{repo}">source</a>' if repo else ""
    return f"""<title>Jimmy's French Habit Tracker</title><style>{CSS}</style>
<div class="wrap">
<header>
  <h1>Jimmy's French Habit Tracker</h1>
  <p>{start:%d %b %Y} – {end:%d %b %Y} · {len(df)} days tracked · rebuilt {stamp}</p>
</header>

<section><div class="tiles">{tile_html}</div></section>

<section>
  <h2>Study calendar</h2>
  <div class="card">{heatmap_svg(df)}
  <p class="cap">Shaded by estimated minutes studied. Hover a day for the breakdown.</p></div>
</section>

<section>
  <h2>Last 7 days</h2>
  {momentum_block(df)}
</section>

<section>
  <h2>Trend — 7-day rolling average per skill</h2>
  {trend_panels(df)}
</section>

<section>
  <h2>Weekly totals against objective</h2>
  {weekly_panels(df, obj)}
</section>

<section>
  <h2>Skill balance — share of days practised</h2>
  <div class="card">{balance_svg(df, obj)}
  <p class="cap">Vertical tick = average weekly-objective attainment for that skill.</p></div>
</section>

<section>
  <h2>Where the time goes</h2>
  <div class="card">{timesplit_svg(df)}
  <p class="cap">Counts converted to minutes: vocab {A.EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card ·
  grammar {A.EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson ·
  writing {A.EST_MIN_PER_UNIT['Writing']:.0f}min/prompt.</p></div>
</section>

<section>
  <h2>Average minutes by day of week</h2>
  <div class="card">{dow_svg(df)}</div>
</section>

<details><summary>All the numbers</summary>
  <h2 style="margin-top:20px">All-time totals</h2>
  {totals_table}
  <h2 style="margin-top:24px">Weekly totals</h2>
  {weekly_table(df, obj)}
</details>

<p class="foot">Built from a Google Sheet with pandas and hand-drawn SVG · rebuilt daily by GitHub Actions{foot_src}</p>
</div>"""


def build_html(df: pd.DataFrame, obj: pd.DataFrame | None) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"</head><body>{page_body(df, obj)}</body></html>"
    )


def main(argv):
    out = Path("dashboard.html")
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])

    df = A.load_daily_log()
    try:
        obj = A.load_objectives()
    except Exception as e:
        print(f"(objectives unavailable: {e})")
        obj = None

    body_only = "--body-only" in argv
    out.write_text(page_body(df, obj) if body_only else build_html(df, obj), encoding="utf-8")
    print(f"Wrote {out.resolve()}  ({out.stat().st_size/1024:.0f} KB)")
    if "--no-open" not in argv and not body_only:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main(sys.argv[1:])
