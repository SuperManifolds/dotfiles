"""Loophole Labs report toolkit: brand tokens, chart builders, stats, validation.

Import this from a per-report generator script that holds the data at the top and
writes one self-contained HTML file. The point of the split is that the numbers live
in the generator (reviewable, diffable, next to the work) while everything that makes
a page look and behave like ours lives here.

    import brand
    html = brand.head("Queue Latency") + f"<style>{brand.css()}</style>" + body
    brand.validate(html)          # raises on the mistakes that actually happen

Palette is converted from `design/src/styles/colors.css` in the architect monorepo,
which is the source of truth. If that file changes, change these.
"""
from __future__ import annotations

import glob
import math
import os
import re
import statistics as st

# --------------------------------------------------------------------------- brand
# Base palette, hex conversions of the HSL in design/src/styles/colors.css.
PURPLE_0 = "#0B081C"   # --color-base-purple-0, the app background
PURPLE_3 = "#0E0925"   # surface
PURPLE_4 = "#120C2C"
PURPLE_5 = "#140C31"
PURPLE_6 = "#271858"
PURPLE_7 = "#542FC6"   # --color-background-brand
PURPLE_8 = "#7242FF"   # the Loophole purple
PURPLE_9 = "#7E57F4"
PURPLE_12 = "#D1C7FF"
PURPLE_13 = "#E2DBFF"
ARCHITECT = "#D84922"  # --color-text-architect, the accent for architect work
ARCHITECT_HI = "#FF4929"
GREEN = "#31D822"      # semantic pass
RED = "#DF0101"        # semantic fail
BLUE = "#187EEC"
BLACK_0 = "#171717"
GRAY_0, GRAY_1, GRAY_2, GRAY_3 = "#AEAEAE", "#E0E0E0", "#E8E8E8", "#F7F7F7"

# Accent text needs slightly more contrast than accent fills: ARCHITECT is 4.29:1 on
# white, just under AA, so type uses the darker ink and shapes keep the brand hue.
ARCHITECT_INK = "#C8401C"

MONO = "'Commit Mono', ui-monospace, SFMono-Regular, monospace"
SANS = "Inter, 'Helvetica Neue', Arial, sans-serif"


def find_brand_font() -> str | None:
    """Locate Commit Mono. It is not on Google Fonts, so it has to be inlined.

    Order: an explicit override, then a monorepo checkout above the working
    directory, then the usual checkout locations. Returns None if absent, in which
    case `head()` falls back to a Google-hosted mono and says so in a comment.
    """
    env = os.environ.get("LOOPHOLE_BRAND_FONT")
    if env and os.path.exists(env):
        return env
    rel = os.path.join("design", "src", "fonts", "commit-mono-variable.woff2")
    here = os.path.abspath(os.getcwd())
    while True:
        cand = os.path.join(here, rel)
        if os.path.exists(cand):
            return cand
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    for pat in (os.path.expanduser("~/github.com/loopholelabs/*/" + rel),
                os.path.expanduser("~/src/loopholelabs/*/" + rel),
                os.path.expanduser("~/*/loopholelabs/*/" + rel)):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[0]
    return None


def head(title: str, font_path: str | None = "auto") -> str:
    """The <title> and font loading. No doctype/html/head/body: Artifact adds those.

    Inter is the brand sans and Google Fonts is the one host the artifact CSP admits,
    so it is linked. Commit Mono is inlined as a data URI when it can be found.
    """
    import base64
    if font_path == "auto":
        font_path = find_brand_font()
    parts = [
        f"<title>{title}</title>",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    ]
    if font_path:
        with open(font_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        parts.append('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                     'family=Inter:wght@400;500;600;700;800&display=swap">')
        parts.append("<style>@font-face{font-family:'Commit Mono';font-style:normal;"
                     "font-weight:200 500;font-display:swap;"
                     f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}</style>")
    else:
        # No brand mono available: JetBrains Mono is the closest Google-hosted match
        # to Commit Mono's low-contrast terminal shapes. Note the substitution.
        parts.append('<!-- Commit Mono not found; using JetBrains Mono as a stand-in -->')
        parts.append('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
                     'family=Inter:wght@400;500;600;700;800&'
                     'family=JetBrains+Mono:wght@400;500&display=swap">')
    return "\n".join(parts) + "\n"


def css(accent: str = ARCHITECT, accent_ink: str = ARCHITECT_INK) -> str:
    """Tokens plus components.

    The theme pattern is not optional and is the classic source of unreadable
    artifacts: the bare `:root` carries the *complete* light palette, the media query
    and the `[data-theme]` block redefine only tokens, and every component takes its
    colour from a token. A colour whose only definition sits inside a media or
    `[data-theme]` block never applies in the un-stamped "system" state.
    """
    mono_stack = MONO
    return f"""
:root {{
  --purple-0: {PURPLE_0}; --purple-3: {PURPLE_3}; --purple-4: {PURPLE_4};
  --purple-6: {PURPLE_6}; --purple-7: {PURPLE_7}; --purple-8: {PURPLE_8};
  --purple-9: {PURPLE_9}; --purple-12: {PURPLE_12}; --purple-13: {PURPLE_13};
  --green: {GREEN}; --red: {RED}; --blue: {BLUE};
  --black-0: {BLACK_0}; --gray-2: {GRAY_2}; --gray-3: {GRAY_3};

  --bg: {GRAY_3};
  --surface: #FFFFFF;
  --surface-2: {GRAY_2};
  --line: #DCD9E6;
  --line-soft: #E9E7F1;
  --ink: {BLACK_0};
  --ink-2: #4A4756;
  --ink-3: #6E6B7C;
  --brand: {PURPLE_7};
  --brand-ink: {PURPLE_7};
  --accent: {accent};
  --accent-ink: {accent_ink};
  --muted: #6F6B8C;
  --muted-soft: #D9D6E6;
  --ok: #1F9E14;
  --bad: {RED};
  --code-bg: #F1EFF8;
  --shadow: 0 1px 2px rgba(11,8,28,.06), 0 8px 24px rgba(11,8,28,.05);
}}

@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: {PURPLE_0}; --surface: {PURPLE_3}; --surface-2: {PURPLE_4};
    --line: #241C46; --line-soft: #1A1436;
    --ink: #FFFFFF; --ink-2: #C3BAE8; --ink-3: #8E86B4;
    --brand: {PURPLE_8}; --brand-ink: {PURPLE_9};
    --accent: {ARCHITECT_HI}; --accent-ink: {ARCHITECT_HI};
    --muted: #6E67A8; --muted-soft: #211A44;
    --ok: {GREEN}; --bad: #FF5A4A;
    --code-bg: {PURPLE_4};
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.35);
  }}
}}

:root[data-theme="dark"] {{
  --bg: {PURPLE_0}; --surface: {PURPLE_3}; --surface-2: {PURPLE_4};
  --line: #241C46; --line-soft: #1A1436;
  --ink: #FFFFFF; --ink-2: #C3BAE8; --ink-3: #8E86B4;
  --brand: {PURPLE_8}; --brand-ink: {PURPLE_9};
  --accent: {ARCHITECT_HI}; --accent-ink: {ARCHITECT_HI};
  --muted: #6E67A8; --muted-soft: #211A44;
  --ok: {GREEN}; --bad: #FF5A4A;
  --code-bg: {PURPLE_4};
  --shadow: 0 1px 2px rgba(0,0,0,.4), 0 12px 32px rgba(0,0,0,.35);
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: {SANS}; font-size: 17px; line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 28px 120px; }}
.col {{ max-width: 68ch; }}

.mast {{ border-bottom: 1px solid var(--line); padding: 54px 0 34px; margin-bottom: 46px; }}
.eyebrow {{
  font-family: {mono_stack}; font-size: 11.5px; letter-spacing: .16em;
  text-transform: uppercase; color: var(--accent-ink); font-weight: 500;
  display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}}
.eyebrow .sep {{ color: var(--ink-3); }}
h1 {{
  font-size: clamp(2.4rem, 5.6vw, 4.1rem); line-height: 1.02; letter-spacing: -.032em;
  font-weight: 800; margin: 20px 0 0; text-wrap: balance; max-width: 20ch;
}}
h1 .thin {{ color: var(--ink-3); font-weight: 600; }}
.standfirst {{
  font-size: 1.24rem; line-height: 1.5; color: var(--ink-2);
  max-width: 62ch; margin: 22px 0 0; text-wrap: pretty;
}}

.figs {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr));
  gap: 1px; background: var(--line); border: 1px solid var(--line);
  border-radius: 8px; overflow: hidden; margin: 40px 0 0;
}}
.fig {{ background: var(--surface); padding: 20px 22px 18px; }}
.fig .k {{
  font-family: {mono_stack}; font-size: 10.5px; letter-spacing: .13em;
  text-transform: uppercase; color: var(--ink-3);
}}
.fig .v {{
  font-family: {mono_stack}; font-size: 2.05rem; font-weight: 500;
  letter-spacing: -.03em; margin-top: 8px; font-variant-numeric: tabular-nums;
  line-height: 1.05;
}}
.fig .v.accent {{ color: var(--accent-ink); }}
.fig .v.brandc {{ color: var(--brand-ink); }}
.fig .v.okc {{ color: var(--ok); }}
.fig .n {{ font-size: 13px; color: var(--ink-3); margin-top: 4px; }}

section {{ margin-top: 74px; }}
h2 {{
  font-size: clamp(1.55rem, 2.7vw, 2.05rem); letter-spacing: -.022em;
  font-weight: 700; line-height: 1.12; margin: 0 0 6px; text-wrap: balance;
}}
h2 .num {{
  font-family: {mono_stack}; font-size: .52em; font-weight: 500;
  color: var(--accent-ink); vertical-align: 3px; margin-right: 12px; letter-spacing: .06em;
}}
h3 {{ font-size: 1.12rem; font-weight: 700; letter-spacing: -.012em; margin: 40px 0 8px; }}
.dek {{ color: var(--ink-3); font-size: 1.03rem; margin: 0 0 26px; max-width: 66ch; }}
p {{ margin: 0 0 17px; text-wrap: pretty; }}
a {{
  color: var(--brand-ink); text-decoration: none;
  border-bottom: 1px solid color-mix(in srgb, var(--brand-ink) 35%, transparent);
}}
a:hover {{ border-bottom-color: var(--brand-ink); }}
a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }}
code {{
  font-family: {mono_stack}; font-size: .86em; background: var(--code-bg);
  padding: .12em .38em; border-radius: 4px; color: var(--ink);
}}

.panel {{
  background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: 26px 28px 22px; margin: 30px 0; box-shadow: var(--shadow);
}}
.panel > figcaption {{
  font-family: {mono_stack}; font-size: 11px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-3); margin-bottom: 18px;
}}
.panel svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
.chartnote {{ font-size: 13.5px; color: var(--ink-3); margin: 16px 0 0; max-width: 74ch; }}
.scroller {{ overflow-x: auto; }}

.grid {{ stroke: var(--line-soft); stroke-width: 1; }}
.tick, .stripnote, .segnote, .phcount, .rnote {{
  font-family: {mono_stack}; font-size: 12px; fill: var(--ink-3);
}}
.rowlab {{ font-family: {SANS}; font-size: 15px; font-weight: 600; fill: var(--ink); }}
.bar-a {{ fill: var(--muted); }}
.bar-b {{ fill: var(--accent); }}
.whisk {{ stroke: var(--ink); stroke-width: 1.6; opacity: .5; }}
.val {{ font-family: {mono_stack}; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }}
.val-a {{ fill: var(--muted); }}
.val-b {{ fill: var(--accent-ink); }}
.brace {{ fill: none; stroke: var(--ink-3); stroke-width: 1.2; }}
.ratio {{ font-family: {mono_stack}; font-size: 14px; font-weight: 500; fill: var(--ink); }}
.dot-a {{ fill: var(--muted); fill-opacity: .85; }}
.dot-b {{ fill: var(--accent); fill-opacity: .85; }}
.iqr-a {{ fill: var(--muted-soft); }}
.iqr-b {{ fill: color-mix(in srgb, var(--accent) 16%, transparent); }}
.median-a {{ stroke: var(--muted); stroke-width: 2; }}
.median-b {{ stroke: var(--accent-ink); stroke-width: 2; }}
.trend {{ fill: none; stroke-width: 1.4; opacity: .45; }}
.trend-a {{ stroke: var(--muted); }}
.trend-b {{ stroke: var(--accent); }}
.seg-0 {{ fill: var(--muted); }}
.seg-1 {{ fill: var(--accent-ink); }}
.seg-2 {{ fill: var(--brand); }}
.seglab {{ font-family: {mono_stack}; font-size: 15px; font-weight: 500; fill: #FFF; }}
.segname {{ font-family: {SANS}; font-size: 14px; font-weight: 600; fill: var(--ink); }}
.segtotal {{ font-family: {mono_stack}; font-size: 12px; fill: var(--ink-3); }}
.phname {{ font-family: {mono_stack}; font-size: 12.5px; fill: var(--ink-2); }}
.ph-hot {{ fill: var(--accent); }}
.ph-cool {{ fill: var(--brand); opacity: .55; }}
.phval {{ font-family: {mono_stack}; font-size: 12.5px; font-weight: 500; fill: var(--ink); font-variant-numeric: tabular-nums; }}
.phbreak {{ stroke: var(--line); stroke-width: 1; stroke-dasharray: 4 4; }}
.phscale {{ font-family: {mono_stack}; font-size: 11px; fill: var(--accent-ink); letter-spacing: .06em; }}
.rlab {{ font-family: {SANS}; font-size: 15px; font-weight: 600; fill: var(--ink); }}
.rd-ok {{ fill: var(--ok); }}
.rd-bad {{ fill: none; stroke: var(--bad); stroke-width: 2; stroke-dasharray: 3 3; }}
.rcount {{ font-family: {mono_stack}; font-size: 13px; font-weight: 500; }}
.rcount-ok {{ fill: var(--ok); }}
.rcount-bad {{ fill: var(--bad); }}

table {{ border-collapse: collapse; width: 100%; font-size: 14.5px; }}
th, td {{ text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--line-soft); vertical-align: top; }}
th {{
  font-family: {mono_stack}; font-size: 10.5px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-3); font-weight: 500;
  border-bottom: 1px solid var(--line);
}}
td.num, th.num {{ text-align: right; font-family: {mono_stack}; font-variant-numeric: tabular-nums; }}
td.ref {{ white-space: nowrap; font-size: 12.5px; font-family: {mono_stack}; }}
tbody tr:last-child td {{ border-bottom: none; }}
tr.hl td {{ background: color-mix(in srgb, var(--accent) 7%, transparent); }}

pre {{
  font-family: {mono_stack}; font-size: 12.5px; line-height: 1.62; margin: 0;
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 8px;
  padding: 18px 20px; overflow-x: auto; color: var(--ink-2);
}}
pre b {{ color: var(--accent-ink); font-weight: 500; }}
pre i {{ color: var(--ink-3); font-style: normal; }}

ol.trail {{ list-style: none; counter-reset: t; margin: 26px 0 0; padding: 0; }}
ol.trail li {{
  counter-increment: t; position: relative; padding: 0 0 22px 62px;
  border-left: 1px solid var(--line); margin-left: 13px;
}}
ol.trail li:last-child {{ border-left-color: transparent; padding-bottom: 0; }}
ol.trail li::before {{
  content: counter(t, decimal-leading-zero); position: absolute; left: -13px; top: 1px;
  width: 26px; height: 26px; border-radius: 50%; background: var(--surface);
  border: 1px solid var(--line); color: var(--ink-3); font-family: {mono_stack};
  font-size: 11px; font-weight: 500; display: grid; place-items: center;
}}
ol.trail li .what {{ font-weight: 700; display: block; margin-bottom: 2px; }}
ol.trail li .how {{ color: var(--ink-2); font-size: 15.5px; }}

ul.spec {{ margin: 4px 0 0; padding-left: 22px; }}
ul.spec li {{ margin-bottom: 9px; color: var(--ink-2); }}
ul.spec li strong {{ color: var(--ink); }}
ul.limits {{ list-style: none; margin: 22px 0 0; padding: 0; }}
ul.limits li {{
  padding: 14px 0 14px 34px; border-bottom: 1px solid var(--line-soft);
  position: relative; color: var(--ink-2); font-size: 15.5px;
}}
ul.limits li:last-child {{ border-bottom: none; }}
ul.limits li::before {{
  content: ""; position: absolute; left: 6px; top: 22px; width: 9px; height: 9px;
  border: 1.5px solid var(--accent); border-radius: 2px; transform: rotate(45deg);
}}
ul.limits li strong {{ color: var(--ink); font-weight: 650; }}

.item {{ display: grid; grid-template-columns: 1fr 200px; gap: 8px 26px; padding: 17px 0; border-bottom: 1px solid var(--line-soft); }}
.item:last-child {{ border-bottom: none; }}
.item .t {{ font-weight: 650; }}
.item .d {{ color: var(--ink-2); font-size: 15px; grid-column: 1; }}
.item .refs {{ grid-row: 1 / span 2; grid-column: 2; font-family: {mono_stack}; font-size: 12.5px; color: var(--ink-3); text-align: right; }}
@media (max-width: 720px) {{
  .item {{ grid-template-columns: 1fr; }}
  .item .refs {{ grid-row: auto; grid-column: 1; text-align: left; }}
}}

.foot {{
  margin-top: 84px; padding-top: 28px; border-top: 1px solid var(--line);
  font-size: 14px; color: var(--ink-3); display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 26px;
}}
.foot .k {{
  font-family: {mono_stack}; font-size: 10.5px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--ink-3); display: block; margin-bottom: 6px;
}}
.foot code {{ background: none; padding: 0; font-size: 13px; color: var(--ink-2); }}
"""


# ---------------------------------------------------------------------- statistics
def pct(xs, f):
    """Linear-interpolated percentile, the convention numpy and dashboards use."""
    xs = sorted(xs)
    i = f * (len(xs) - 1)
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (i - lo) * (xs[hi] - xs[lo])


def describe(xs):
    xs = sorted(xs)
    q = st.quantiles(xs, n=4)
    sd = st.stdev(xs) if len(xs) > 1 else 0.0
    mean = st.mean(xs)
    return dict(n=len(xs), lo=xs[0], hi=xs[-1], mean=mean, med=st.median(xs), sd=sd,
                q1=q[0], q3=q[2], iqr=q[2] - q[0], p90=pct(xs, .90), p95=pct(xs, .95),
                cv=(sd / mean * 100) if mean else 0.0,
                sem=sd / math.sqrt(len(xs)) if xs else 0.0)


_T95 = ((2, 4.30), (3, 3.18), (4, 2.78), (6, 2.45), (10, 2.23),
        (15, 2.13), (20, 2.09), (30, 2.04), (60, 2.00))


def welch(a, b):
    """Difference of means with a 95% CI, for two independent samples."""
    da, db = describe(a), describe(b)
    diff = da["mean"] - db["mean"]
    se = math.sqrt(da["sem"] ** 2 + db["sem"] ** 2)
    den = (da["sem"] ** 4 / (da["n"] - 1)) + (db["sem"] ** 4 / (db["n"] - 1))
    dof = ((da["sem"] ** 2 + db["sem"] ** 2) ** 2 / den) if den else float("inf")
    crit = 1.96
    for lim, t in _T95:
        if dof <= lim:
            crit = t
            break
    return dict(diff=diff, lo=diff - crit * se, hi=diff + crit * se, dof=dof)


def mann_whitney(a, b):
    """U and z without assuming normality. U == n1*n2 or 0 means no overlap."""
    merged = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = {}, 0
    while i < len(merged):
        j = i
        while j + 1 < len(merged) and merged[j + 1][0] == merged[i][0]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = r
        i = j + 1
    ra = sum(ranks[k] for k, (_, t) in enumerate(merged) if t == 0)
    n1, n2 = len(a), len(b)
    u = ra - n1 * (n1 + 1) / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    return dict(u=u, z=(u - n1 * n2 / 2) / sigma if sigma else 0.0,
                separated=u in (0, n1 * n2), umax=n1 * n2)


# -------------------------------------------------------------------------- charts
def _svg(w, h, label):
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{label}" '
            f'preserveAspectRatio="xMidYMid meet">')


def bar_compare(rows, unit="ms", label="comparison", top=None, ratio_note=True):
    """Means on one axis with min-max whiskers. rows: [(name, describe(), 'a'|'b')].

    The headline comparison chart. Whiskers are the observed range, not error bars,
    and the caption should say so.
    """
    w, h = 1000, 60 + 70 * len(rows) + 60
    x0, x1 = 150, 960
    top = top or max(r[1]["hi"] for r in rows) * 1.035

    def x(v):
        return x0 + (v / top) * (x1 - x0)

    s = [_svg(w, h, label)]
    stepv = 10 ** int(math.log10(top))
    if top / stepv < 3:
        stepv /= 2
    t = 0
    while t <= top:
        s.append(f'<line class="grid" x1="{x(t):.1f}" y1="34" x2="{x(t):.1f}" y2="{h - 54}"/>')
        s.append(f'<text class="tick" x="{x(t):.1f}" y="{h - 32}" text-anchor="middle">{t:g}</text>')
        t += stepv
    ends = []
    for i, (name, d, cls) in enumerate(rows):
        y, bh = 60 + i * 70, 40
        s.append(f'<rect class="bar-{cls}" x="{x0}" y="{y}" width="{x(d["mean"]) - x0:.1f}" height="{bh}" rx="3"/>')
        s.append(f'<line class="whisk" x1="{x(d["lo"]):.1f}" y1="{y + bh / 2}" x2="{x(d["hi"]):.1f}" y2="{y + bh / 2}"/>')
        for v in (d["lo"], d["hi"]):
            s.append(f'<line class="whisk" x1="{x(v):.1f}" y1="{y + 10}" x2="{x(v):.1f}" y2="{y + bh - 10}"/>')
        s.append(f'<text class="rowlab" x="{x0 - 16}" y="{y + bh / 2 + 5}" text-anchor="end">{name}</text>')
        s.append(f'<text class="val val-{cls}" x="{x(d["mean"]) + 14:.1f}" y="{y + bh / 2 + 6}">{d["mean"]:.0f} {unit}</text>')
        ends.append(x(d["mean"]))
    if ratio_note and len(rows) == 2:
        a, b = rows[0][1]["mean"], rows[1][1]["mean"]
        xa, xb = min(ends), max(ends)
        ym = 60 + 70 - 12
        s.append(f'<path class="brace" d="M {xa:.1f} {ym + 8} L {xa:.1f} {ym} L {xb:.1f} {ym} L {xb:.1f} {ym + 8}"/>')
        s.append(f'<text class="ratio" x="{(xa + xb) / 2:.1f}" y="{ym - 8}" text-anchor="middle">'
                 f'&#8722;{abs(a - b):.0f} {unit} &#183; {max(a, b) / min(a, b):.2f}&#215;</text>')
    s.append("</svg>")
    return "\n".join(s)


def beeswarm(data, d, cls, lo, hi, label="samples", step=None):
    """Every sample as a dot, displaced only where neighbours would collide.

    Vertical position encodes local density, never collection order. Height is
    computed from the rows actually needed so nothing escapes the viewBox.
    """
    w, x0, x1 = 1000, 70, 950
    span = hi - lo

    def x(v):
        return x0 + ((v - lo) / span) * (x1 - x0)

    r, gap = 4.2, 9.4
    rows = []
    for v in sorted(data):
        cx = x(v)
        for row in rows:
            if cx - row[-1] > 2 * r + 0.6:
                row.append(cx)
                break
        else:
            rows.append([cx])
    spread = ((len(rows) - 1) // 2 + 1) * gap
    mid = 34 + spread
    h = int(mid + spread + 58)
    top_y, bot_y = mid - spread + 4, mid + spread - 4
    s = [_svg(w, h, label)]
    step = step or (span / 6)
    t = lo
    while t <= hi + 1e-9:
        s.append(f'<line class="grid" x1="{x(t):.1f}" y1="{top_y - 8:.1f}" x2="{x(t):.1f}" y2="{bot_y + 8:.1f}"/>')
        s.append(f'<text class="tick" x="{x(t):.1f}" y="{bot_y + 30:.1f}" text-anchor="middle">{t:g}</text>')
        t += step
    s.append(f'<rect class="iqr-{cls}" x="{x(d["q1"]):.1f}" y="{top_y:.1f}" '
             f'width="{x(d["q3"]) - x(d["q1"]):.1f}" height="{bot_y - top_y:.1f}" rx="2"/>')
    s.append(f'<line class="median-{cls}" x1="{x(d["med"]):.1f}" y1="{top_y - 6:.1f}" '
             f'x2="{x(d["med"]):.1f}" y2="{bot_y + 6:.1f}"/>')
    for ri, row in enumerate(rows):
        off = ((ri + 1) // 2) * gap * (1 if ri % 2 else -1)
        for cx in row:
            s.append(f'<circle class="dot-{cls}" cx="{cx:.1f}" cy="{mid + off:.1f}" r="{r}"/>')
    s.append(f'<text class="stripnote" x="{x(d["med"]):.1f}" y="{top_y - 14:.1f}" '
             f'text-anchor="middle">median {d["med"]:.0f}</text>')
    s.append("</svg>")
    return "\n".join(s)


def stacked(parts, unit="ms", label="decomposition", total_note=""):
    """One bar split by owner. parts: [(name, value, note)].

    Use it to stop a headline figure being read as one component's cost. If any part
    is a residual rather than a measurement, say so in its note.
    """
    total = sum(p[1] for p in parts)
    w, h = 1000, 190
    x0, x1 = 20, 980
    x = x0
    s = [_svg(w, h, label)]
    for i, (name, v, note) in enumerate(parts):
        bw = (v / total) * (x1 - x0)
        tx = x + bw / 2
        s.append(f'<rect class="seg seg-{i % 3}" x="{x:.1f}" y="30" width="{bw:.1f}" height="52" rx="3"/>')
        s.append(f'<text class="seglab" x="{tx:.1f}" y="62" text-anchor="middle">{v:g} {unit}</text>')
        s.append(f'<text class="segname" x="{tx:.1f}" y="104" text-anchor="middle">{name}</text>')
        s.append(f'<text class="segnote" x="{tx:.1f}" y="124" text-anchor="middle">{note}</text>')
        x += bw
    s.append(f'<text class="segtotal" x="{x1}" y="164" text-anchor="end">'
             f'{total:g} {unit}{" &#183; " + total_note if total_note else ""}</text>')
    s.append("</svg>")
    return "\n".join(s)


def hbars(rows, unit="ms", label="breakdown", split=0, hot_above=None):
    """Ranked horizontal bars. rows: [(name, value, annotation)].

    `split` puts the first N rows on their own scale and magnifies the rest, which is
    how a long tail stays legible when one or two entries dominate. Say in the caption
    that widths are not comparable across the break.
    """
    rowh, w = 30, 1000
    x0, x1 = 250, 830
    head_rows, tail = rows[:split] if split else [], rows[split:] if split else rows
    top_head = head_rows[0][1] if head_rows else None
    top_tail = tail[0][1]
    hot_above = hot_above if hot_above is not None else (top_tail * 0.4)
    h = 30 + len(rows) * rowh + (54 if split else 20)
    s = [_svg(w, h, label)]

    def emit(i, name, v, note, scale, cls):
        y = 24 + i * rowh
        bw = max((v / scale) * (x1 - x0), 1.5)
        s.append(f'<text class="phname" x="{x0 - 14}" y="{y + 15}" text-anchor="end">{name}</text>')
        s.append(f'<rect class="ph ph-{cls}" x="{x0}" y="{y + 3}" width="{bw:.1f}" height="17" rx="2"/>')
        s.append(f'<text class="phval" x="{x0 + bw + 12:.1f}" y="{y + 16}">{v:g} {unit}</text>')
        if note:
            s.append(f'<text class="phcount" x="{w - 10}" y="{y + 16}" text-anchor="end">{note}</text>')

    for i, (name, v, note) in enumerate(head_rows):
        emit(i, name, v, note, top_head, "hot")
    off = len(head_rows)
    if split:
        yb = 24 + off * rowh + 12
        s.append(f'<line class="phbreak" x1="{x0 - 200}" y1="{yb}" x2="{w - 10}" y2="{yb}"/>')
        s.append(f'<text class="phscale" x="{x0 - 14}" y="{yb + 15}" text-anchor="end">'
                 f'below, scale &#215;{top_head / top_tail:.0f}</text>')
        off += 1
    for i, (name, v, note) in enumerate(tail):
        emit(i + off, name, v, note, top_tail, "hot" if v >= hot_above else "cool")
    s.append("</svg>")
    return "\n".join(s)


def dot_matrix(rows, label="outcomes"):
    """Pass/fail as dots. rows: [(name, total, ok, note)]. Filled = ok, dashed = not.

    Better than a percentage when n is small, because the reader sees the n.
    """
    w = 1000
    h = 44 + 84 * len(rows) + 20
    s = [_svg(w, h, label)]
    for r, (name, total, ok, note) in enumerate(rows):
        y = 44 + r * 84
        s.append(f'<text class="rlab" x="20" y="{y - 12}">{name}</text>')
        if note:
            s.append(f'<text class="rnote" x="980" y="{y - 12}" text-anchor="end">{note}</text>')
        pitch = min(25, (w - 60) / max(total, 1))
        for i in range(total):
            s.append(f'<circle class="rd rd-{"ok" if i < ok else "bad"}" '
                     f'cx="{26 + i * pitch:.1f}" cy="{y + 10}" r="{min(8.5, pitch / 2.6):.1f}"/>')
        s.append(f'<text class="rcount rcount-{"ok" if ok == total else "bad"}" x="20" y="{y + 46}">'
                 f'{ok} of {total}</text>')
    s.append("</svg>")
    return "\n".join(s)


def series(sets, lo, hi, label="values by index", xlabel="sample index", unit=""):
    """Value against index for one or more sets, to show whether a run drifts.

    sets: [(name, [values], 'a'|'b')]. A flat line is the point: it rules out
    warm-up and thermal effects inside the measurement window.
    """
    w, h = 1000, 260
    x0, x1 = 66, 962
    n = max(len(v) for _, v, _ in sets)

    def x(i):
        return x0 + ((i - 1) / max(n - 1, 1)) * (x1 - x0)

    def y(v):
        return 210 - ((v - lo) / (hi - lo)) * 176

    s = [_svg(w, h, label)]
    stepv = (hi - lo) / 3
    t = lo + stepv
    while t < hi:
        s.append(f'<line class="grid" x1="{x0}" y1="{y(t):.1f}" x2="{x1}" y2="{y(t):.1f}"/>')
        s.append(f'<text class="tick" x="{x0 - 12}" y="{y(t) + 4:.1f}" text-anchor="end">{t:.0f}{unit}</text>')
        t += stepv
    for i in sorted({1, n // 4, n // 2, 3 * n // 4, n}):
        if i >= 1:
            s.append(f'<text class="tick" x="{x(i):.1f}" y="236" text-anchor="middle">{i}</text>')
    s.append(f'<text class="tick" x="{(x0 + x1) / 2:.1f}" y="256" text-anchor="middle">{xlabel}</text>')
    for name, vals, cls in sets:
        pts = " ".join(f"{x(i + 1):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        s.append(f'<polyline class="trend trend-{cls}" points="{pts}"/>')
        for i, v in enumerate(vals):
            s.append(f'<circle class="dot-{cls}" cx="{x(i + 1):.1f}" cy="{y(v):.1f}" r="4"/>')
        s.append(f'<text class="rowlab" x="{x1}" y="{y(st.mean(vals)) - 16:.1f}" text-anchor="end">{name}</text>')
    s.append("</svg>")
    return "\n".join(s)


# ----------------------------------------------------------------------- validation
def _lum(hx):
    hx = hx.lstrip("#")
    r, g, b = (int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def validate(html, strict=True):
    """The checks that catch the mistakes that actually happen. Returns a problem list.

    1. A token used but not defined in the bare `:root` renders one theme's text on
       the other theme's ground for every viewer on the default "system" setting.
    2. Unbalanced containers silently swallow the rest of the page.
    3. SVG content outside its own viewBox is invisible or clipped.
    4. A doctype/html/body wrapper is added at publish time; including one nests.
    """
    problems = []
    m = re.search(r":root\s*\{(.*?)\n\}", html, re.S)
    if not m:
        problems.append("no bare :root block: the light palette has nowhere to live")
    else:
        defined = set(re.findall(r"(--[\w-]+)\s*:", m.group(1)))
        used = set(re.findall(r"var\((--[\w-]+)", html))
        missing = sorted(u for u in used if u not in defined)
        if missing:
            problems.append(f"tokens used but not defined in bare :root: {missing}")
    for tag in ("div", "section", "figure", "svg", "table", "tbody", "tr", "td", "th",
                "ul", "ol", "li", "pre", "p", "figcaption"):
        o = len(re.findall(r"<" + tag + r"[\s>]", html))
        c = len(re.findall(r"</" + tag + r">", html))
        if o != c:
            problems.append(f"unbalanced <{tag}>: {o} open, {c} close")
    for sm in re.finditer(r'<svg viewBox="0 0 ([\d.]+) ([\d.]+)".*?</svg>', html, re.S):
        vh = float(sm.group(2))
        body = sm.group(0)
        ys = [float(v) for v in re.findall(r'c?y="([-\d.]+)"', body)]
        out = [v for v in ys if v < -2 or v > vh + 2]
        if out:
            problems.append(f"{len(out)} SVG y-coords outside a viewBox of height {vh:g}")
    if re.search(r"<!doctype|<html[\s>]|<body[\s>]", html, re.I):
        problems.append("remove <!doctype>/<html>/<body>: the publisher adds the skeleton")
    if "background" not in html:
        problems.append("body needs an explicit background from a token, or it "
                        "borrows the host's theme")
    if strict and problems:
        raise SystemExit("brand.validate failed:\n  " + "\n  ".join(problems))
    return problems
