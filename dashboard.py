"""
French habit tracker - visual dashboard.

Pulls fresh data through analytics.py and renders a single self-contained
`dashboard.html` (inline CSS + hand-built SVG, plus one Google Fonts request
for Nunito), then opens it in your browser.

    python dashboard.py                # build dashboard.html and open it
    python dashboard.py --no-open      # just build the file
    python dashboard.py --out foo.html # write somewhere else

Re-run it whenever you want the latest picture - it always reflects the sheet.
"""

from __future__ import annotations

import os
import re
import sys
import html
import math
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
# Personal blurb shown at the top of the dashboard, under the header. Edit the
# text below to describe your French background and the materials/resources
# you use - separate paragraphs with a blank line. Re-run `python dashboard.py`
# (or `python build.py`) afterwards to regenerate the page.
# --------------------------------------------------------------------------- #
ABOUT_TEXT = """Prior to learning French seriously, my foundation consisted of French I, II, and III
in high school (shoutout Mme Mooney) and a 450-day Duolingo streak starting summer 2024.

For listening practice, I'm currently using French-language podcasts such as *InnerFrench* and
*Little Talk in Slow French*, complemented by *L'After Foot* (a footy talk show) and
miscellaneous YouTube videos featuring more natural French. For vocabulary, I use
Anki flashcards, and for grammar, KwizIQ. I'm also (slowly) reading *Jaune : histoire d'une
couleur* by Michel Pastoureau, which discusses the cultural, social, and artistic history of the
color yellow from ancient times to today. For writing, I answer miscellaneous prompts, trying to vary
tenses and incorporate recently learned words and phrases. My speaking practice so far has come from
conversations with colleagues who are also learning French, general shadowing, AI chatbots, and a few Italki
lessons."""

# --------------------------------------------------------------------------- #
# tiny svg / formatting helpers
# --------------------------------------------------------------------------- #
def esc(x) -> str:
    return html.escape(str(x), quote=True)


def fmt(n, nd=0) -> str:
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return "-"
    if nd == 0:
        return f"{round(n):,}"
    return f"{n:,.{nd}f}"


def _nice_max(v: float) -> float:
    """Round a raw max up to a clean axis ceiling (1/2/2.5/5/10 x a power of ten)."""
    if v <= 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if v <= step:
            return step
    return 10 * mag


def _month_ticks(dates: pd.DatetimeIndex) -> list[tuple[int, str]]:
    """(integer position, month label) for every 1st-of-month within `dates`."""
    out = []
    y, mo = dates[0].year, dates[0].month
    end = dates[-1]
    while True:
        cand = pd.Timestamp(year=y, month=mo, day=1)
        if cand > end:
            break
        if cand >= dates[0]:
            try:
                out.append((int(dates.get_loc(cand)), f"{cand:%b}"))
            except KeyError:
                pass
        mo += 1
        if mo > 12:
            mo, y = 1, y + 1
    return out


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
#    axes instead of a text delta: a max gridline + value, an end value, and
#    a tick for the 1st of each month that falls within the series.
# --------------------------------------------------------------------------- #
def _panel(title: str, unit: str, dates: pd.DatetimeIndex, series: np.ndarray) -> str:
    W, H = 340, 140
    ml, mr, mt, mb = 34, 10, 24, 22
    n = len(series)
    raw_max = float(series.max()) if n else 0.0
    ymax = _nice_max(raw_max * 1.08)
    xs = lambda i: ml + (W - ml - mr) * (i / (n - 1) if n > 1 else 0)
    ys = lambda v: H - mb - (H - mt - mb) * (v / ymax if ymax else 0)

    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(series))
    area = f"{ml},{ys(0):.1f} " + pts + f" {xs(n-1):.1f},{ys(0):.1f}"
    end_x, end_y = xs(n - 1), ys(series[-1])
    y0 = ys(0)
    y_max_px = ys(ymax)
    nd = 0 if ymax == int(ymax) else 1

    ticks = []
    for pos, lab in _month_ticks(dates):
        x = xs(pos)
        ticks.append(f'<line class="p-tick" x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0+4:.1f}"/>')
        ticks.append(f'<text class="p-xlab" x="{x:.1f}" y="{H-6}">{lab}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" class="sk-{title.lower()}" '
        f'aria-label="{esc(title)}, 7-day rolling average, {esc(unit)} per day">'
        f'<text class="p-title" x="{ml-4}" y="14">{esc(title)}</text>'
        f'<text class="p-unit" x="{W-mr}" y="14" text-anchor="end">{esc(unit)}/day</text>'
        f'<line class="p-grid" x1="{ml}" y1="{y_max_px:.1f}" x2="{W-mr}" y2="{y_max_px:.1f}"/>'
        f'<text class="p-axis" x="{ml-6}" y="{y_max_px-4:.1f}" text-anchor="end">{fmt(ymax,nd)}</text>'
        f'<line class="p-base" x1="{ml}" y1="{y0:.1f}" x2="{W-mr}" y2="{y0:.1f}"/>'
        f'<polygon class="p-area" points="{area}"/>'
        f'<polyline class="p-line" points="{pts}"/>'
        f'<circle class="p-end" cx="{end_x:.1f}" cy="{end_y:.1f}" r="3"/>'
        f'<text class="p-endlab" x="{end_x:.1f}" y="{end_y-8:.1f}" text-anchor="end">{fmt(series[-1],1)}</text>'
        f'{"".join(ticks)}'
        f"</svg>"
    )


def trend_panels(df: pd.DataFrame) -> str:
    roll = df[SKILLS].rolling(7, min_periods=3).mean().bfill()
    out = [_panel(s, UNIT[s], df.index, roll[s].to_numpy()) for s in SKILLS]
    return f'<div class="grid">{"".join(out)}</div>'


# --------------------------------------------------------------------------- #
# 3. weekly totals, small multiples
# --------------------------------------------------------------------------- #
def weekly_panels(df: pd.DataFrame) -> str:
    wk = A.weekly(df)
    out = [_bars_panel(s, f"weekly {UNIT[s]}", wk[s].to_numpy(dtype=float), wk.index) for s in SKILLS]
    return f'<div class="grid">{"".join(out)}</div>'


def _month_ticks_weekly(dates: pd.DatetimeIndex) -> list[tuple[int, str]]:
    """(bar position, month label) at the first week starting in each new month.

    Skips a tick that lands within 2 bars of the previous one - which only
    happens for the very first couple of weeks when the series starts near a
    month boundary - so the labels never overlap.
    """
    out = []
    last_mo = None
    for i, d in enumerate(dates):
        if d.month != last_mo:
            if out and i - out[-1][0] < 2:
                out[-1] = (i, f"{d:%b}")
            else:
                out.append((i, f"{d:%b}"))
            last_mo = d.month
    return out


def _bars_panel(title: str, sub: str, vals: np.ndarray, dates: pd.DatetimeIndex | None = None) -> str:
    W, H = 340, 140
    ml, mr, mt, mb = 10, 10, 30, 22
    n = len(vals)
    ymax = vals.max() * 1.15 or 1
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

    ticks = []
    if dates is not None:
        for pos, lab in _month_ticks_weekly(dates):
            x = ml + pos * slot + slot / 2
            ticks.append(f'<line class="p-tick" x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0+4:.1f}"/>')
            ticks.append(f'<text class="p-xlab" x="{x:.1f}" y="{H-6}">{lab}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" class="sk-{title.lower()}" '
        f'aria-label="{esc(title)} {esc(sub)}">'
        f'<text class="p-title" x="{ml}" y="13">{esc(title)}</text>'
        f'<text class="p-sub" x="{ml}" y="25">{esc(sub)}</text>'
        f'<line class="p-base" x1="{ml}" y1="{y0}" x2="{W-mr}" y2="{y0}"/>'
        f'{"".join(bars)}{"".join(ticks)}</svg>'
    )


# --------------------------------------------------------------------------- #
# 3b. monthly view - monthly hours + consistency by month, single-series bars
#     with a real axis and one label per bar (there are only ever a handful).
# --------------------------------------------------------------------------- #
def _month_bars_panel(title, index, vals, ymax, axis_label, tooltip_fmt) -> str:
    W, H = 420, 160
    ml, mr, mt, mb = 34, 10, 26, 24
    n = max(len(vals), 1)
    slot = (W - ml - mr) / n
    bw = min(40, slot - 10)
    y0 = H - mb
    ys = lambda v: y0 - (H - mt - mb) * (v / ymax if ymax else 0)

    bars = []
    for i, (d, v) in enumerate(zip(index, vals)):
        x = ml + i * slot + (slot - bw) / 2
        yv = ys(v)
        bars.append(
            f'<rect class="b-bar" x="{x:.1f}" y="{yv:.1f}" width="{bw:.1f}" '
            f'height="{max(0, y0-yv):.1f}" rx="3"><title>{d:%b %Y}: {tooltip_fmt(v)}</title></rect>'
        )
        bars.append(f'<text class="d-lab" x="{x+bw/2:.1f}" y="{y0+15}">{d:%b}</text>')
    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="{esc(title)}">'
        f'<text class="p-title" x="{ml-4}" y="14">{esc(title)}</text>'
        f'<line class="p-grid" x1="{ml}" y1="{ys(ymax):.1f}" x2="{W-mr}" y2="{ys(ymax):.1f}"/>'
        f'<text class="p-axis" x="{ml-6}" y="{ys(ymax)-4:.1f}" text-anchor="end">{esc(axis_label)}</text>'
        f'<line class="p-base" x1="{ml}" y1="{y0}" x2="{W-mr}" y2="{y0}"/>'
        f'{"".join(bars)}</svg>'
    )


def monthly_panels(df: pd.DataFrame) -> str:
    mh = A.monthly_hours(df)
    cm = A.consistency_by_month(df)
    ymax_h = _nice_max(float(mh.max()) * 1.15) if len(mh) else 1.0
    nd = 0 if ymax_h == int(ymax_h) else 1
    left = _month_bars_panel(
        "Monthly hours", mh.index, mh.to_numpy(), ymax_h,
        f"{fmt(ymax_h, nd)}h", lambda v: f"{fmt(v,1)}h",
    )
    right = _month_bars_panel(
        "Consistency by month", cm.index, cm["pct"].to_numpy(), 100.0,
        "100%", lambda v: f"{fmt(v,0)}%",
    )
    return f'<div class="grid2">{left}{right}</div>'


# --------------------------------------------------------------------------- #
# 3c. cumulative progress - one full-width running total across the period
# --------------------------------------------------------------------------- #
def cumulative_svg(df: pd.DataFrame) -> str:
    cum = A.cumulative_hours(df)
    W, H = 880, 180
    ml, mr, mt, mb = 40, 12, 20, 24
    n = len(cum)
    vals = cum.to_numpy()
    ymax = _nice_max(float(vals[-1]) * 1.08) if n else 1.0
    xs = lambda i: ml + (W - ml - mr) * (i / (n - 1) if n > 1 else 0)
    ys = lambda v: H - mb - (H - mt - mb) * (v / ymax if ymax else 0)
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(vals))
    area = f"{ml},{ys(0):.1f} " + pts + f" {xs(n-1):.1f},{ys(0):.1f}"
    y0 = ys(0)
    y_max_px = ys(ymax)
    nd = 0 if ymax == int(ymax) else 1
    ex, ey = xs(n - 1), ys(vals[-1])

    ticks = []
    for pos, lab in _month_ticks(cum.index):
        x = xs(pos)
        ticks.append(f'<line class="p-tick" x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{y0+4:.1f}"/>')
        ticks.append(f'<text class="p-xlab" x="{x:.1f}" y="{H-6}">{lab}</text>')

    return (
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-label="Cumulative estimated hours of French study over time">'
        f'<text class="p-unit" x="{W-mr}" y="14" text-anchor="end">hours, cumulative</text>'
        f'<line class="p-grid" x1="{ml}" y1="{y_max_px:.1f}" x2="{W-mr}" y2="{y_max_px:.1f}"/>'
        f'<text class="p-axis" x="{ml-8}" y="{y_max_px-4:.1f}" text-anchor="end">{fmt(ymax,nd)}h</text>'
        f'<line class="p-base" x1="{ml}" y1="{y0:.1f}" x2="{W-mr}" y2="{y0:.1f}"/>'
        f'<text class="p-axis" x="{ml-8}" y="{y0+3:.1f}" text-anchor="end">0</text>'
        f'<polygon class="p-area" points="{area}"/>'
        f'<polyline class="p-line" points="{pts}"/>'
        f'<circle class="p-end" cx="{ex:.1f}" cy="{ey:.1f}" r="3.5"/>'
        f'<text class="p-endlab" x="{ex:.1f}" y="{ey-9:.1f}" text-anchor="end">{fmt(vals[-1])}h</text>'
        f'{"".join(ticks)}'
        f"</svg>"
    )


# --------------------------------------------------------------------------- #
# 4. skill balance - horizontal bars, % of days touched
# --------------------------------------------------------------------------- #
def balance_svg(df: pd.DataFrame) -> str:
    bal = A.skill_balance(df).sort_values("days_touched_pct", ascending=True)
    rows = list(bal.index)
    W = 560
    rowh = 34
    H = rowh * len(rows) + 20
    ml, mr = 96, 60
    span = W - ml - mr
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Share of days each skill was practiced">']
    for i, s in enumerate(rows):
        y = 14 + i * rowh
        pct = bal.loc[s, "days_touched_pct"]
        bw = span * pct / 100
        out.append(f'<text class="h-cat" x="{ml-10}" y="{y+13}">{esc(s)}</text>')
        out.append(f'<rect class="h-track" x="{ml}" y="{y}" width="{span}" height="18" rx="4"/>')
        out.append(f'<rect class="h-fill sk-{s.lower()}" x="{ml}" y="{y}" width="{bw:.1f}" height="18" rx="4">'
                   f'<title>{esc(s)}: practiced on {pct:.0f}% of days</title></rect>')
        out.append(f'<text class="h-val" x="{ml+bw+6:.1f}" y="{y+13}">{pct:.0f}%</text>')
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- #
# 5. where the time goes - stacked bar of estimated minutes, largest first
# --------------------------------------------------------------------------- #
SLOT = {s: f"--sk-{s.lower()}" for s in SKILLS}  # matches the sheet's own column colours


def timesplit_svg(df: pd.DataFrame) -> str:
    est = A.estimated_minutes(df).sum()          # minutes per skill
    total = float(est.sum()) or 1.0
    order = est.sort_values(ascending=False).index.tolist()
    W, H = 560, 96

    x = 0.0
    segs = []
    for s in order:
        frac = est[s] / total
        wpx = (W - 4) * frac
        segs.append(
            f'<rect x="{x:.1f}" y="0" width="{max(0, wpx-2):.1f}" height="24" rx="3" '
            f'fill="var({SLOT[s]})"><title>{esc(s)}: {est[s]/60:.1f} h '
            f'({frac*100:.0f}%)</title></rect>'
        )
        x += wpx

    # legend: two rows of three, in the same largest-first order as the bar
    leg = []
    for i, s in enumerate(order):
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
            f'aria-label="Share of estimated study time across all six skills, largest first">'
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
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Average minutes practiced by day of week">']
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


def _line_panel(ox, oy, title, sub, series):
    ml, mr, mt, mb = 6, 6, 30, 12
    n = len(series)
    ymax = float(series.max()) * 1.15 or 1
    xs = lambda i: ox + ml + (_PW - ml - mr) * (i / (n - 1) if n > 1 else 0)
    ys = lambda v: oy + _PH - mb - (_PH - mt - mb) * (v / ymax)
    pts = " ".join(f"{xs(i):.1f},{ys(v):.1f}" for i, v in enumerate(series))
    area = f"{ox+ml},{ys(0):.1f} {pts} {xs(n-1):.1f},{ys(0):.1f}"
    ex, ey = xs(n - 1), ys(series[-1])
    return (
        f'<g class="sk-{title.lower()}">'
        f'<text class="p-title" x="{ox+ml}" y="{oy+13}">{esc(title)}</text>'
        f'<text class="p-sub" x="{ox+ml}" y="{oy+25}">{esc(sub)}</text>'
        f'<polygon class="p-area" points="{area}"/>'
        f'<polyline class="p-line" points="{pts}"/>'
        f'<circle class="p-end" cx="{ex:.1f}" cy="{ey:.1f}" r="3"/>'
        f'</g>'
    )


def _col_panel(ox, oy, title, sub, vals):
    ml, mr, mt, mb = 6, 6, 30, 12
    n = len(vals)
    ymax = float(vals.max()) * 1.15 or 1
    slot = (_PW - ml - mr) / n
    bw = min(14, slot - 2)
    y0 = oy + _PH - mb
    ys = lambda v: y0 - (_PH - mt - mb) * (v / ymax)
    bars = "".join(
        f'<rect class="b-bar" x="{ox+ml+i*slot+(slot-bw)/2:.1f}" y="{ys(v):.1f}" '
        f'width="{bw:.1f}" height="{max(0, y0-ys(v)):.1f}" rx="2"/>'
        for i, v in enumerate(vals)
    )
    return (
        f'<g class="sk-{title.lower()}">'
        f'<text class="p-title" x="{ox+ml}" y="{oy+13}">{esc(title)}</text>'
        f'<text class="p-sub" x="{ox+ml}" y="{oy+25}">{esc(sub)}</text>'
        f'<line class="p-base" x1="{ox+ml}" y1="{y0}" x2="{ox+_PW-mr}" y2="{y0}"/>'
        f'{bars}'
        f'</g>'
    )


def trend_grid_svg(df: pd.DataFrame) -> str:
    roll = df[SKILLS].rolling(7, min_periods=3).mean().bfill()
    head, origin, *_ = _grid_shell(len(SKILLS), "7-day rolling average per skill")
    body = []
    for i, s in enumerate(SKILLS):
        ox, oy = origin(i)
        body.append(_line_panel(ox, oy, s, f"{UNIT[s]}/day", roll[s].to_numpy()))
    return head + "".join(body) + "</svg>"


def weekly_grid_svg(df: pd.DataFrame) -> str:
    wk = A.weekly(df)
    head, origin, *_ = _grid_shell(len(SKILLS), "Weekly totals per skill")
    body = []
    for i, s in enumerate(SKILLS):
        ox, oy = origin(i)
        body.append(_col_panel(ox, oy, s, f"weekly {UNIT[s]}", wk[s].to_numpy(dtype=float)))
    return head + "".join(body) + "</svg>"


# --------------------------------------------------------------------------- #
# assemble page
# --------------------------------------------------------------------------- #
# Flat, editorial palette in the spirit of jimmysieja.github.io (Nunito, hairline
# borders, no card fills). Aggregate charts (calendar, cumulative, day-of-week,
# monthly) stay single-accent blue; anything broken out per skill - trend,
# weekly, skill balance, momentum, "where the time goes", table headers -
# picks up that skill's own colour, matched to the tracking sheet's column
# fills (see SLOT / --sk-* below).
_TOK_LIGHT = (
    "--font:'Nunito',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    "--bg:#ffffff;--ink:#1a1a1a;--ink2:#43454a;--muted:#666666;--border:#e3e3e3;"
    "--link:#3a6fd0;--link-hover:#29508f;--accent:#3a6fd0;"
    "--sk-listening:#ccc319;--sk-grammar:#358d35;--sk-vocab:#1fa4d6;"
    "--sk-reading:#7a49ca;--sk-writing:#cd519f;--sk-speaking:#d05739;"
    "--heat-0:#edecea;--heat-1:#cfe0f5;--heat-2:#9dc0e9;--heat-3:#6693d4;--heat-4:#3a6fd0;"
    "--fr-blue:#3a6fd0;--fr-red:#b5534a;"
)
_TOK_DARK = (
    "--bg:#15161a;--ink:#e7e7e7;--ink2:#c3c4c8;--muted:#9b9b9b;--border:#2c2e34;"
    "--link:#7ea9ec;--link-hover:#a9c6f5;--accent:#7ea9ec;"
    "--sk-listening:#f4ee7b;--sk-grammar:#8bd08b;--sk-vocab:#82d0ed;"
    "--sk-reading:#b498e1;--sk-writing:#db99c3;--sk-speaking:#de907c;"
    "--heat-0:#202126;--heat-1:#22334c;--heat-2:#2c4d75;--heat-3:#3f6ea3;--heat-4:#7ea9ec;"
    "--fr-blue:#7ea9ec;--fr-red:#d38178;"
)

# rules that style the hand-built SVG marks - shared by the page and by the
# standalone SVG files exported for the README.
CHART_CSS = """
/* per-skill colour switch: set via a sk-* class on a wrapping element, read
   by the mark rules below (falls back to the neutral accent on aggregate
   charts that aren't scoped to one skill, e.g. the calendar or day-of-week) */
.sk-listening{--pc:var(--sk-listening)}
.sk-grammar{--pc:var(--sk-grammar)}
.sk-vocab{--pc:var(--sk-vocab)}
.sk-reading{--pc:var(--sk-reading)}
.sk-writing{--pc:var(--sk-writing)}
.sk-speaking{--pc:var(--sk-speaking)}
.p-title{fill:var(--ink);font-size:12px;font-weight:700}
.p-sub{fill:var(--muted);font-size:10px}
.p-unit{fill:var(--muted);font-size:10px}
.p-axis{fill:var(--muted);font-size:9.5px}
.p-grid{stroke:var(--border);stroke-width:1;stroke-dasharray:2,3}
.p-base{stroke:var(--border);stroke-width:1}
.p-tick{stroke:var(--border);stroke-width:1}
.p-xlab{fill:var(--muted);font-size:9px;text-anchor:middle}
.p-line{fill:none;stroke:var(--pc,var(--accent));stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.p-area{fill:var(--pc,var(--accent));opacity:.12}
.p-end{fill:var(--pc,var(--accent));stroke:var(--bg);stroke-width:2}
.p-endlab{fill:var(--ink2);font-size:10px;text-anchor:end;font-weight:700}
.b-bar{fill:var(--pc,var(--accent))}
.b-bar:hover{fill:var(--link-hover);opacity:.9}
.d-lab{fill:var(--muted);font-size:10px;text-anchor:middle}
.d-val{fill:var(--ink2);font-size:10px;text-anchor:middle;font-weight:700}
/* heatmap */
.hm-mon{fill:var(--muted);font-size:10px}
.hm-dow{fill:var(--muted);font-size:9px;text-anchor:end}
rect:hover{opacity:.82}
/* horizontal bars */
.h-cat{fill:var(--ink);font-size:12px;text-anchor:end;dominant-baseline:middle}
.h-track{fill:var(--border);opacity:.5}
.h-fill{fill:var(--pc,var(--accent))}
.h-val{fill:var(--ink2);font-size:11px;font-weight:700;dominant-baseline:middle}
.ts-lab{fill:var(--ink);font-size:11px;font-weight:700}
.ts-val{fill:var(--muted);font-size:11px}
"""

# page chrome - layout only, not used by the standalone SVGs
_LAYOUT_CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);
  font-size:15px;line-height:1.65;font-weight:400;-webkit-font-smoothing:antialiased;
  text-rendering:optimizeLegibility}
a{color:var(--link);text-decoration:none}
a:hover{color:var(--link-hover);text-decoration:underline}

.accent-bar{height:3px;display:flex}
.accent-bar span{flex:1 1 0}
.accent-bar span:nth-child(1){background:var(--fr-blue)}
.accent-bar span:nth-child(2){background:var(--border)}
.accent-bar span:nth-child(3){background:var(--fr-red)}

.wrap{max-width:960px;margin:0 auto;padding:0 24px}

.site-header{border-bottom:1px solid var(--border)}
.site-header .wrap{padding:22px 24px 18px}
.kicker{font-size:13px;font-style:italic;color:var(--muted);margin:0 0 3px}
.head-row{display:flex;align-items:baseline;justify-content:space-between;gap:16px}
h1{font-size:23px;margin:0;font-weight:700;letter-spacing:-.01em;color:var(--ink)}
.meta{margin:9px 0 0;color:var(--muted);font-size:13px}

.theme-toggle{border:0;background:none;padding:2px;color:var(--muted);cursor:pointer;
  display:inline-flex;align-self:center;flex:none}
.theme-toggle:hover{color:var(--ink)}
.theme-toggle svg{width:16px;height:16px;display:block}
.theme-toggle .moon{display:none}
:root[data-theme="dark"] .theme-toggle .sun{display:none}
:root[data-theme="dark"] .theme-toggle .moon{display:block}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .theme-toggle .sun{display:none}
  :root:not([data-theme="light"]) .theme-toggle .moon{display:block}
}

main.wrap{padding-top:32px;padding-bottom:8px}
section{margin-top:40px}
h2{font-size:16px;font-weight:700;color:var(--ink);margin:0 0 14px}
.cap{font-size:12px;color:var(--muted);margin:10px 0 0}

.about{margin-top:26px;color:var(--ink2);font-size:14px}
.about p{margin:0 0 10px}
.about p:last-child{margin-bottom:0}

.frame{border:1px solid var(--border);border-radius:6px;padding:20px}

.stats{display:flex;flex-wrap:wrap;gap:26px 40px;padding:20px 0;
  border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.stat{min-width:108px}
.stat .lab{font-size:12.5px;color:var(--muted)}
.stat .val{font-size:25px;font-weight:700;letter-spacing:-.01em;margin-top:3px;color:var(--ink)}
.stat .sub{font-size:12px;color:var(--muted);margin-top:2px}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}
.grid svg,.grid2 svg{border:1px solid var(--border);border-radius:6px;padding:8px 6px 4px;display:block}

.mom{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:18px}
.mom .m{border-left:3px solid var(--pc,var(--border));padding-left:10px}
.mom .sk{font-size:12.5px;color:var(--muted)}
.mom .big{font-size:20px;font-weight:700;margin-top:3px;color:var(--ink)}
.mom .big .unit{font-size:12px;font-weight:400;color:var(--muted)}

table{border-collapse:collapse;width:100%;margin-top:6px;font-size:13px;
  font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:7px 10px;border-bottom:1px solid var(--border)}
th:first-child,td:first-child{text-align:left}
th{font-weight:700;color:var(--ink2)}

details{margin-top:36px;font-size:13px;color:var(--ink2)}
summary{cursor:pointer;color:var(--link);font-weight:700}
summary:hover{color:var(--link-hover)}

.site-footer{border-top:1px solid var(--border);margin-top:44px}
.site-footer .wrap{padding:16px 24px 40px;display:flex;flex-wrap:wrap;
  justify-content:space-between;gap:6px 16px;font-size:12.5px;color:var(--muted)}
.site-footer a{color:var(--muted)}
.site-footer a:hover{color:var(--ink)}

@media (max-width:640px){
  .head-row{flex-wrap:wrap}
  .stats{gap:20px 28px}
}
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
    # a bg-coloured backdrop so the file is readable on any page, not just
    # the matching GitHub theme
    bg = f'<rect x="0" y="0" width="100%" height="100%" fill="{pal["--bg"]}"/>'
    style = f"<style>{sub(CHART_CSS)}</style>"
    body = sub(body).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    cut = body.index(">") + 1
    return body[:cut] + style + bg + body[cut:]


def export_assets(df: pd.DataFrame, outdir="assets") -> list[Path]:
    """Write light+dark standalone SVGs used by the README."""
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    charts = {
        "calendar": heatmap_svg(df),
        "skills": balance_svg(df),
        "time-split": timesplit_svg(df),
        "weekday": dow_svg(df),
        "trend": trend_grid_svg(df),
        "weekly": weekly_grid_svg(df),
    }
    written = []
    for name, svg in charts.items():
        for theme in ("light", "dark"):
            p = out / f"{name}-{theme}.svg"
            p.write_text(standalone_svg(svg, theme), encoding="utf-8")
            written.append(p)
    return written


def momentum_block(df: pd.DataFrame) -> str:
    """Last 7 days per skill - just the total, no vs-prior-week comparison."""
    m = A.momentum(df)
    cards = []
    for s in SKILLS:
        r = m.loc[s]
        cards.append(
            f'<div class="m sk-{s.lower()}"><div class="sk">{esc(s)}</div>'
            f'<div class="big">{fmt(r["last_7d_total"])}<span class="unit"> {esc(UNIT[s])}</span></div></div>'
        )
    return f'<div class="mom">{"".join(cards)}</div>'


def weekly_table(df: pd.DataFrame) -> str:
    wk = A.weekly(df)
    head = "".join(
        f'<th style="border-bottom:3px solid var(--sk-{s.lower()})">{s}</th>' for s in SKILLS
    )
    body = []
    for wkstart, row in wk.iterrows():
        tds = "".join(f"<td>{fmt(row[s])}</td>" for s in SKILLS)
        body.append(f"<tr><td>{wkstart:%d %b %Y}</td>{tds}</tr>")
    return f"<table><thead><tr><th>Week starting</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def monthly_table(df: pd.DataFrame) -> str:
    mo = A.monthly(df)
    head = "".join(
        f'<th style="border-bottom:3px solid var(--sk-{s.lower()})">{s}</th>' for s in SKILLS
    )
    body = []
    for mstart, row in mo.iterrows():
        tds = "".join(f"<td>{fmt(row[s])}</td>" for s in SKILLS)
        body.append(f"<tr><td>{mstart:%b %Y}</td>{tds}</tr>")
    return f"<table><thead><tr><th>Month</th>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


_ITALIC_RE = re.compile(r"\*([^*]+)\*")


def about_block(text: str) -> str:
    """Plain-text paragraphs (blank line = new paragraph, *word* = italics)."""
    paras = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    out = []
    for p in paras:
        body = _ITALIC_RE.sub(r"<em>\1</em>", esc(" ".join(p.split())))
        out.append(f"<p>{body}</p>")
    return "".join(out)


def page_body(df: pd.DataFrame) -> str:
    """The <title> + <style> + content, with no document skeleton.

    Usable as-is for a Claude Artifact (which supplies <!doctype>/<head>/<body>);
    build_html() wraps this in a standalone document for local viewing."""
    s = A.streaks(df)
    t = A.totals(df)
    start, end = df.index[0].date(), df.index[-1].date()
    total_hours = t["hours"].dropna().sum()
    est_hours = t["est_hours"].sum()
    week_est_min = float(A.estimated_minutes(df).iloc[-7:].sum().sum())
    month_est_min = float(A.estimated_minutes(df).iloc[-30:].sum().sum())
    month_days = min(30, len(df))
    aw = A.avg_weekly_hours(df)

    tiles = [
        ("Consistency", f'{s["consistency_pct"]:.0f}%', f'{s["active_days"]} of {s["tracked_days"]} days'),
        ("Total time", f"{est_hours:.0f}h", ""),
        ("Median weekly time", f'{aw["median"]:.1f}h', ""),
        ("Last 7 days", f"{week_est_min/60:.1f}h", f"{week_est_min/7:.0f} min/day"),
        ("Last 30 days", f"{month_est_min/60:.1f}h", f"{month_est_min/month_days:.0f} min/day"),
    ]
    tile_html = "".join(
        f'<div class="stat"><div class="lab">{esc(l)}</div><div class="val">{esc(v)}</div>'
        + (f'<div class="sub">{esc(sub)}</div>' if sub else "")
        + "</div>"
        for l, v, sub in tiles
    )

    # totals table
    trows = []
    for sk, r in t.iterrows():
        hrs = f'{r["hours"]:.1f} h' if pd.notna(r["hours"]) else "—"
        trows.append(
            f'<tr><td style="border-left:3px solid var(--sk-{sk.lower()});padding-left:7px">{sk}</td>'
            f"<td>{fmt(r['total'])} {UNIT[sk]}</td><td>{hrs}</td>"
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
    repo_link = f'<a href="{esc(repo)}">source</a>' if repo else ""
    footer_links = " · ".join(
        x for x in [repo_link, '<a href="https://jimmysieja.github.io">jimmysieja.github.io</a>'] if x
    )

    fonts = (
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/'
        'css2?family=Nunito:ital,wght@0,400;0,600;0,700;1,400&display=swap">'
    )
    theme_init = (
        "<script>(function(){try{var t=localStorage.getItem('fh-theme');"
        "if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>"
    )
    theme_toggle_script = (
        "<script>(function(){"
        "var btn=document.getElementById('fh-theme-btn');if(!btn)return;"
        "btn.addEventListener('click',function(){"
        "var root=document.documentElement;"
        "var sysDark=matchMedia('(prefers-color-scheme: dark)').matches;"
        "var cur=root.getAttribute('data-theme')||(sysDark?'dark':'light');"
        "var next=cur==='dark'?'light':'dark';"
        "root.setAttribute('data-theme',next);"
        "try{localStorage.setItem('fh-theme',next);}catch(e){}"
        "});"
        "})();</script>"
    )
    theme_icons = (
        '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2.2M12 19.8V22M4.2 4.2l1.55 1.55M18.25 18.25l1.55 1.55'
        'M2 12h2.2M19.8 12H22M4.2 19.8l1.55-1.55M18.25 5.75l1.55-1.55"/></svg>'
        '<svg class="moon" viewBox="0 0 24 24" fill="currentColor">'
        '<path d="M20.5 14.7A8.5 8.5 0 1 1 9.3 3.5a7 7 0 0 0 11.2 11.2Z"/></svg>'
    )

    return f"""<title>Jimmy's French Habit Tracker</title>
{fonts}
<style>{CSS}</style>
{theme_init}
<div class="accent-bar"><span></span><span></span><span></span></div>
<header class="site-header"><div class="wrap">
  <div class="kicker">Carnet de bord</div>
  <div class="head-row">
    <h1>Jimmy's French Habit Tracker</h1>
    <button id="fh-theme-btn" class="theme-toggle" type="button" aria-label="Toggle color theme">{theme_icons}</button>
  </div>
  <p class="meta">{start:%d %b %Y} – {end:%d %b %Y} · {len(df)} days tracked · updated {stamp}</p>
</div></header>

<main class="wrap">

<section class="about">{about_block(ABOUT_TEXT)}</section>

<section><div class="stats">{tile_html}</div></section>

<section>
  <h2>Study calendar</h2>
  <div class="frame">{heatmap_svg(df)}</div>
  <p class="cap">Shaded by estimated minutes studied. Hover a day for the breakdown.</p>
</section>

<section>
  <h2>Last 7 days</h2>
  {momentum_block(df)}
</section>

<section>
  <h2>Weekly totals</h2>
  {weekly_panels(df)}
</section>

<section>
  <h2>Trend — 7-day rolling average per skill</h2>
  {trend_panels(df)}
</section>

<section>
  <h2>Where the time goes</h2>
  <div class="frame">{timesplit_svg(df)}</div>
  <p class="cap">Counts converted to minutes: vocab {A.EST_MIN_PER_UNIT['Vocab']*60:.0f}s/card ·
  grammar {A.EST_MIN_PER_UNIT['Grammar']:.0f}min/lesson ·
  writing {A.EST_MIN_PER_UNIT['Writing']:.0f}min/prompt.</p>
</section>

<section>
  <h2>Skill balance — share of days practiced</h2>
  <div class="frame">{balance_svg(df)}</div>
</section>

<section>
  <h2>Monthly view</h2>
  {monthly_panels(df)}
</section>

<section>
  <h2>Average minutes by day of week</h2>
  <div class="frame">{dow_svg(df)}</div>
</section>

<section>
  <h2>Cumulative progress</h2>
  <div class="frame">{cumulative_svg(df)}</div>
</section>

<details><summary>All the numbers</summary>
  <h2 style="margin-top:20px">All-time totals</h2>
  {totals_table}
  <h2 style="margin-top:24px">Weekly totals</h2>
  {weekly_table(df)}
  <h2 style="margin-top:24px">Monthly totals</h2>
  {monthly_table(df)}
</details>

</main>

<footer class="site-footer"><div class="wrap">
  <span>Built from a Google Sheet with pandas and hand-drawn SVG · rebuilt daily by GitHub Actions</span>
  <span>{footer_links}</span>
</div></footer>
{theme_toggle_script}"""


def build_html(df: pd.DataFrame) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"</head><body>{page_body(df)}</body></html>"
    )


def main(argv):
    out = Path("dashboard.html")
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])

    df = A.load_daily_log()

    body_only = "--body-only" in argv
    out.write_text(page_body(df) if body_only else build_html(df), encoding="utf-8")
    print(f"Wrote {out.resolve()}  ({out.stat().st_size/1024:.0f} KB)")
    if "--no-open" not in argv and not body_only:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main(sys.argv[1:])
