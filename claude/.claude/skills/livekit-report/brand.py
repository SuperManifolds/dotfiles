"""LiveKit report toolkit: Bytes tokens, fonts, chart builders, stats, validation.

Import this from a per-report generator script that holds the data at the top and
writes one self-contained HTML file. The numbers live in the generator (reviewable,
diffable, next to the work); everything that makes a page look like LiveKit lives here.

    import brand
    html = brand.head("Queue Latency") + f"<style>{brand.css()}</style>" + body
    brand.validate(html)          # raises on the mistakes that actually happen

Tokens are copied from Bytes, LiveKit's design system, in the `livekit/web` monorepo:
`packages/bytes-core/colors/raw-colors.ts` and `two-face-colors.ts`. If those move on,
update TOKENS below; `python3 brand.py --check <path to web checkout>` diffs them.

Dark is the default theme. The bare `:root` carries the dark palette and only an
explicit `data-theme="light"` (or `data-lk-theme="light"`) switches to light, matching
LiveKit's own surfaces where dark is canonical.
"""
from __future__ import annotations

import base64
import math
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
ASSETS = os.path.join(HERE, "assets")

# --------------------------------------------------------------------------- brand
# Bytes semantic and chart tokens as (dark, light). Names are the Bytes names, so a
# value can be checked against two-face-colors.ts by eye or with --check.
TOKENS = {
    # surfaces: bg1 is the page, bg2 raised (code, figures), bg3 inert chrome
    "bg0": ("#000000", "#FFFFFF"),
    "bg1": ("#070707", "#FDFDFC"),
    "bg2": ("#131313", "#EFEFEC"),
    "bg3": ("#1F1F1F", "#E2E2DF"),
    # text: fg0 max contrast, fg1 body, fg2 de-emphasised, fg3 captions, fg4 disabled
    "fg0": ("#FFFFFF", "#000000"),
    "fg1": ("#CCCCCC", "#3B3B3B"),
    "fg2": ("#B2B2B2", "#4D4D4D"),
    "fg3": ("#999999", "#636363"),
    "fg4": ("#666666", "#707070"),
    "separator1": ("#202020", "#DBDBD8"),
    "separator2": ("#30302F", "#BDBDBB"),
    # brand accent: cyan in dark, blue in light. One emphasis per screen.
    "accent": ("#1FD5F9", "#002CF2"),
    "accent2": ("#15889F", "#395CF9"),
    "fgAccentSecondary1": ("#DC85FF", "#7A15A2"),
    "bgAccentPrimary1": ("#051518", "#E2EBFD"),
    "separatorAccentPrimary": ("#012A32", "#CADBFC"),
    # state
    "fgSuccess": ("#23DE6B", "#00753B"),
    "fgModerate": ("#FFB752", "#9D4D06"),
    "fgSerious1": ("#FF7566", "#B32909"),
    "bgSuccess1": ("#001905", "#D1FADF"),
    "bgModerate1": ("#1A0E04", "#FAEDD1"),
    "bgSerious1": ("#1F0E0B", "#FAE6E6"),
    # charts: cycle chart1..chart8 in series order; pin meaning to the state slots
    "chart1": ("#1FD5F9", "#002CF2"),
    "chart2": ("#BA1FF9", "#9A1ACE"),
    "chart3": ("#F97A1F", "#DB5E06"),
    "chart4": ("#DC85FF", "#DC85FF"),
    "chart5": ("#009E4F", "#009E4F"),
    "chart6": ("#395CF9", "#1FD5F9"),
    "chart7": ("#F9E71F", "#DBC906"),
    "chart8": ("#FA4C39", "#FA4C39"),
    "chartNeutral": ("#666666", "#707070"),
    "chartNeutralSecondary": ("#30302F", "#BDBDBB"),
    "chartSerious": ("#FF7566", "#B32909"),
    "chartSuccess": ("#23DE6B", "#00753B"),
    "chartModerate": ("#FFB752", "#9D4D06"),
    # agent pipeline stages: name the same stage in the same colour everywhere
    "fgLLM": ("#FA4CFA", "#DB06DB"),
    "fgRealtime": ("#FA954C", "#DB5E06"),
    "fgSTT": ("#04A489", "#06DBB7"),
    "fgTTS": ("#A3FA4C", "#54A404"),
    "fgTool": ("#FA4CA3", "#DB0670"),
    "fgEOU": ("#FAEC4C", "#DBC906"),
    # syntax
    "codeAccent": ("#07B6DA", "#0F1F66"),
    "codePurple": ("#DC85FF", "#9A1ACE"),
    "codeGreen": ("#23DE6B", "#00753B"),
    "codeAmber": ("#FFB752", "#833E01"),
}

# Report-level roles, mapped onto Bytes tokens. Series "a" is the baseline, "b" ours.
ROLES = {
    "data-a": "chartNeutral",
    "data-a-soft": "chartNeutralSecondary",
    "data-b": "chart1",
}

# Ink for a label on a filled chart mark: whichever of these contrasts more with the
# fill, per token and per theme, emitted as `--on-<token>`.
INKS = ("#070707", "#FFFFFF")

# Pipeline stage keys accepted by `stacked`, mapped to their token.
STAGES = {"llm": "fgLLM", "realtime": "fgRealtime", "stt": "fgSTT", "tts": "fgTTS",
          "tool": "fgTool", "eou": "fgEOU"}

SANS = "'Public Sans', ui-sans-serif, system-ui, sans-serif"
DISPLAY = "'TWK Everett', 'Public Sans', ui-sans-serif, system-ui, sans-serif"
MONO = "'CommitMono', ui-monospace, SFMono-Regular, Menlo, monospace"

# Everett ships static cuts; the "medium" file is registered at 600 in LiveKit's apps.
EVERETT = {300: "everett-light.woff2", 400: "everett-regular.woff2",
           600: "everett-medium.woff2", 700: "everett-bold.woff2"}
COMMIT_MONO = "commit-mono-variable-font.woff2"


FONTS_SRC = "repos/livekit/web/contents/apps/cloud/fonts"


def _font(name: str) -> str:
    """Path to a brand font, fetched from `livekit/web` with `gh` on first use.

    The fonts are licensed and come from a private repo, so `fonts/` is gitignored
    rather than shipped with the skill.
    """
    path = os.path.join(FONTS, name)
    if os.path.exists(path):
        return path
    import subprocess
    os.makedirs(FONTS, exist_ok=True)
    try:
        data = subprocess.run(
            ["gh", "api", "-H", "Accept: application/vnd.github.raw", f"{FONTS_SRC}/{name}"],
            check=True, capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        err = getattr(e, "stderr", b"") or b""
        raise SystemExit(f"brand font {name} missing and fetching it from livekit/web "
                         f"failed (needs `gh` with access to the repo): {err.decode().strip() or e}")
    with open(path, "wb") as f:
        f.write(data)
    return path


def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def head(title: str, display_weights=(300, 400)) -> str:
    """The <title> and font loading. No doctype/html/head/body: Artifact adds those.

    Public Sans is on Google Fonts, the one host the artifact CSP admits, so it links.
    CommitMono and TWK Everett are inlined from `fonts/` beside this file,
    fetched from `livekit/web` on first use. Only the
    Everett cuts in `display_weights` are embedded; each is ~55 KB before base64.
    """
    parts = [
        f"<title>{title}</title>",
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Public+Sans:ital,wght@0,100..900;1,100..900&display=swap">',
    ]
    faces = [
        "@font-face{font-family:'CommitMono';font-style:normal;font-weight:100 700;"
        f"font-display:swap;src:url(data:font/woff2;base64,{_b64(_font(COMMIT_MONO))})"
        " format('woff2');}"
    ]
    for w in display_weights:
        faces.append(
            f"@font-face{{font-family:'TWK Everett';font-style:normal;font-weight:{w};"
            f"font-display:swap;src:url(data:font/woff2;base64,"
            f"{_b64(_font(EVERETT[w]))}) format('woff2');}}")
    parts.append("<style>" + "".join(faces) + "</style>")
    return "\n".join(parts) + "\n"


def logo(height: int = 20, mark: bool = False) -> str:
    """The LiveKit wordmark (or the reduced LK mark), inline, coloured by currentColor."""
    with open(os.path.join(ASSETS, "mark.svg" if mark else "wordmark.svg")) as f:
        svg = f.read()
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    svg = re.sub(r"<title[^>]*>.*?</title>", "", svg, flags=re.S)
    return svg.replace("<svg", f'<svg class="logo" style="height:{height}px;width:auto" '
                               'aria-label="LiveKit"', 1)


def _vars(idx: int) -> str:
    lines = [f"  --{k}: {v[idx]};" for k, v in TOKENS.items()]
    lines += [f"  --{k}: var(--{v});" for k, v in ROLES.items()]
    for k, v in TOKENS.items():
        if k.startswith("chart") or k in STAGES.values():
            ink = max(INKS, key=lambda c: contrast(c, v[idx]))
            lines.append(f"  --on-{k}: {ink};")
    return "\n".join(lines)


_DOTS = {  # Bytes bg-dot-pattern-1: a 1px square on a 3px pitch
    0: "PHN2ZyB3aWR0aD0iMyIgaGVpZ2h0PSIzIiB2aWV3Qm94PSIwIDAgMyAzIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHg9IjEiIHk9IjEiIHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9InJnYigzMiwgMzIsIDMyKSIvPjwvc3ZnPg==",
    1: "PHN2ZyB3aWR0aD0iMyIgaGVpZ2h0PSIzIiB2aWV3Qm94PSIwIDAgMyAzIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHg9IjEiIHk9IjEiIHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9InJnYigyMTksIDIxOSwgMjE2KSIvPjwvc3ZnPg==",
}


def css() -> str:
    """Tokens plus components.

    Every component takes its colour from a token, and every token is defined in the
    bare `:root` (the dark palette). The light block redefines tokens only. A colour
    whose only definition sits inside the light block never applies by default.
    """
    light = (f"{_vars(1)}\n  --dots: url(data:image/svg+xml;base64,{_DOTS[1]});\n"
             "  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 8px 24px rgba(0,0,0,.04);\n"
             "  color-scheme: light;")
    return f"""
:root {{
{_vars(0)}
  --dots: url(data:image/svg+xml;base64,{_DOTS[0]});
  --shadow: none;
  color-scheme: dark;
}}

:root[data-theme="light"], :root[data-lk-theme="light"] {{
{light}
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg1); color: var(--fg1);
  font-family: {SANS}; font-size: 16px; line-height: 1.7; letter-spacing: .01em;
  -webkit-font-smoothing: antialiased; font-feature-settings: 'rlig' 1, 'calt' 1;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 28px 120px; }}
.col {{ max-width: 68ch; }}
.caps {{ font-family: {MONO}; text-transform: uppercase; letter-spacing: .05em; }}

.mast {{
  border-bottom: 1px solid var(--separator1); padding: 40px 0 40px; margin-bottom: 48px;
  position: relative;
}}
.mast::before {{
  content: ""; position: absolute; inset: 0 -28px; background-image: var(--dots);
  opacity: .9; z-index: -1;
  -webkit-mask: radial-gradient(ellipse 60% 90% at 70% 40%, #000 0%, transparent 72%);
  mask: radial-gradient(ellipse 60% 90% at 70% 40%, #000 0%, transparent 72%);
}}
.mast .logo {{ color: var(--fg0); display: block; margin-bottom: 44px; }}
.eyebrow {{
  font-family: {MONO}; font-size: 12px; letter-spacing: .05em; text-transform: uppercase;
  color: var(--fg3); display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
}}
.eyebrow .sep {{ color: var(--fg4); }}
.eyebrow .on {{ color: var(--accent); }}
h1 {{
  font-family: {DISPLAY}; font-weight: 300; color: var(--fg0);
  font-size: clamp(2.25rem, 5.4vw, 4.5rem); line-height: 1.04; letter-spacing: -.02em;
  margin: 18px 0 0; text-wrap: balance; max-width: 20ch;
}}
h1 .hl {{ color: var(--accent); }}
.standfirst {{
  font-size: 1.25rem; line-height: 1.6; color: var(--fg2);
  max-width: 62ch; margin: 22px 0 0; text-wrap: pretty;
}}

.figs {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(178px, 1fr));
  gap: 1px; background: var(--separator1); border: 1px solid var(--separator1);
  border-radius: 6px; overflow: hidden; margin: 40px 0 0;
}}
.fig {{ background: var(--bg1); padding: 20px 22px 18px; }}
.fig .k {{
  font-family: {MONO}; font-size: 11px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--fg3);
}}
.fig .v {{
  font-family: {MONO}; font-size: 2.25rem; font-weight: 400; color: var(--fg0);
  letter-spacing: -.03em; margin-top: 8px; font-variant-numeric: tabular-nums;
  line-height: 1.05;
}}
.fig .v.accent {{ color: var(--accent); }}
.fig .v.okc {{ color: var(--fgSuccess); }}
.fig .v.badc {{ color: var(--fgSerious1); }}
.fig .n {{ font-size: 13px; color: var(--fg3); margin-top: 6px; }}

section {{ margin-top: 80px; }}
h2 {{
  font-family: {DISPLAY}; font-weight: 400; color: var(--fg0);
  font-size: clamp(1.875rem, 3vw, 2.25rem); letter-spacing: -.015em;
  line-height: 1.15; margin: 0 0 8px; text-wrap: balance;
}}
h2 .num {{
  font-family: {MONO}; font-size: .42em; font-weight: 400; letter-spacing: .05em;
  color: var(--fg3); vertical-align: 6px; margin-right: 14px;
}}
h3 {{ font-size: 1.125rem; font-weight: 600; color: var(--fg0); margin: 40px 0 8px; letter-spacing: 0; }}
.dek {{ color: var(--fg3); font-size: 1.0625rem; margin: 0 0 26px; max-width: 66ch; }}
p {{ margin: 0 0 16px; text-wrap: pretty; }}
strong {{ color: var(--fg0); font-weight: 600; }}
a {{
  color: var(--fg0); text-decoration: underline; text-underline-offset: 3px;
  text-decoration-color: var(--separator2); text-decoration-thickness: 1px;
}}
a:hover {{ color: var(--accent); text-decoration-color: var(--accent); }}
a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }}
code {{
  font-family: {MONO}; font-size: .86em; background: var(--bg2);
  padding: .12em .38em; border-radius: 4px; color: var(--fg0);
}}

.panel {{
  background: var(--bg1); border: 1px solid var(--separator1); border-radius: 8px;
  padding: 26px 28px 22px; margin: 30px 0; box-shadow: var(--shadow);
}}
.panel > figcaption {{
  font-family: {MONO}; font-size: 11px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--fg3); margin-bottom: 18px;
}}
.panel svg {{ width: 100%; height: auto; display: block; overflow: visible; }}
.chartnote {{ font-size: 13.5px; color: var(--fg3); margin: 16px 0 0; max-width: 74ch; }}
.scroller {{ overflow-x: auto; }}
.key {{ display: flex; flex-wrap: wrap; gap: 18px; font-size: 13px; color: var(--fg2); margin: 0 0 14px; }}
.key i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 7px; vertical-align: -1px; }}

.grid {{ stroke: var(--separator1); stroke-width: 1; }}
.tick, .stripnote, .segnote, .phcount, .rnote {{
  font-family: {MONO}; font-size: 12px; fill: var(--fg3);
}}
.rowlab {{ font-family: {SANS}; font-size: 15px; font-weight: 600; fill: var(--fg0); }}
.bar-a {{ fill: var(--data-a); }}
.bar-b {{ fill: var(--data-b); }}
.whisk {{ stroke: var(--fg0); stroke-width: 1.5; opacity: .45; }}
.val {{ font-family: {MONO}; font-size: 15px; font-weight: 500; font-variant-numeric: tabular-nums; }}
.val-a {{ fill: var(--fg2); }}
.val-b {{ fill: var(--data-b); }}
.brace {{ fill: none; stroke: var(--fg3); stroke-width: 1.2; }}
.ratio {{ font-family: {MONO}; font-size: 14px; font-weight: 500; fill: var(--fg0); }}
.dot-a {{ fill: var(--data-a); fill-opacity: .9; }}
.dot-b {{ fill: var(--data-b); fill-opacity: .85; }}
.iqr-a {{ fill: color-mix(in srgb, var(--data-a) 22%, transparent); }}
.iqr-b {{ fill: color-mix(in srgb, var(--data-b) 16%, transparent); }}
.median-a {{ stroke: var(--fg2); stroke-width: 2; }}
.median-b {{ stroke: var(--data-b); stroke-width: 2; }}
.trend {{ fill: none; stroke-width: 1.5; opacity: .5; }}
.trend-a {{ stroke: var(--data-a); }}
.trend-b {{ stroke: var(--data-b); }}
.seglab {{ font-family: {MONO}; font-size: 15px; font-weight: 500; }}
.segname {{ font-family: {SANS}; font-size: 14px; font-weight: 600; fill: var(--fg0); }}
.segtotal {{ font-family: {MONO}; font-size: 12px; fill: var(--fg3); }}
.phname {{ font-family: {MONO}; font-size: 12.5px; fill: var(--fg2); }}
.ph-hot {{ fill: var(--data-b); }}
.ph-cool {{ fill: var(--data-a); }}
.phval {{ font-family: {MONO}; font-size: 12.5px; font-weight: 500; fill: var(--fg0); font-variant-numeric: tabular-nums; }}
.phbreak {{ stroke: var(--separator2); stroke-width: 1; stroke-dasharray: 4 4; }}
.phscale {{ font-family: {MONO}; font-size: 11px; fill: var(--fg3); letter-spacing: .05em; }}
.rlab {{ font-family: {SANS}; font-size: 15px; font-weight: 600; fill: var(--fg0); }}
.rd-ok {{ fill: var(--chartSuccess); }}
.rd-bad {{ fill: none; stroke: var(--chartSerious); stroke-width: 2; stroke-dasharray: 3 3; }}
.rcount {{ font-family: {MONO}; font-size: 13px; font-weight: 500; }}
.rcount-ok {{ fill: var(--fgSuccess); }}
.rcount-bad {{ fill: var(--fgSerious1); }}

table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--separator1); vertical-align: top; }}
td {{ color: var(--fg2); }}
th {{
  font-family: {MONO}; font-size: 11px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--fg3); font-weight: 400;
  border-bottom: 1px solid var(--separator2);
}}
td.num, th.num {{ text-align: right; font-family: {MONO}; font-variant-numeric: tabular-nums; }}
td.ref {{ white-space: nowrap; font-size: 12.5px; font-family: {MONO}; }}
tbody tr:last-child td {{ border-bottom: none; }}
tr.sel td {{ background: var(--bg2); color: var(--fg0); }}

.badge {{
  display: inline-block; font-family: {MONO}; font-size: 10.5px; letter-spacing: .05em;
  text-transform: uppercase; padding: 1px 7px; border-radius: 4px; border: 1px solid;
  vertical-align: 1px; white-space: nowrap;
}}
.badge.ok {{ color: var(--fgSuccess); background: var(--bgSuccess1); border-color: color-mix(in srgb, var(--fgSuccess) 30%, transparent); }}
.badge.warn {{ color: var(--fgModerate); background: var(--bgModerate1); border-color: color-mix(in srgb, var(--fgModerate) 30%, transparent); }}
.badge.bad {{ color: var(--fgSerious1); background: var(--bgSerious1); border-color: color-mix(in srgb, var(--fgSerious1) 30%, transparent); }}
.badge.muted {{ color: var(--fg3); background: var(--bg2); border-color: var(--separator2); }}

.decor {{ display: inline-flex; align-items: center; gap: 8px; }}
.decor::before {{ content: ""; width: 2px; height: 12px; border-radius: 1px; background: var(--c, var(--fg3)); }}

pre {{
  font-family: {MONO}; font-size: 12.5px; line-height: 1.62; margin: 0;
  background: var(--bg2); border: 1px solid var(--separator1); border-radius: 6px;
  padding: 18px 20px; overflow-x: auto; color: var(--fg2);
}}
pre b {{ color: var(--codeAccent); font-weight: 500; }}
pre i {{ color: var(--fg4); font-style: normal; }}

ol.trail {{ list-style: none; counter-reset: t; margin: 26px 0 0; padding: 0; }}
ol.trail li {{
  counter-increment: t; position: relative; padding: 0 0 22px 62px;
  border-left: 1px solid var(--separator1); margin-left: 13px;
}}
ol.trail li:last-child {{ border-left-color: transparent; padding-bottom: 0; }}
ol.trail li::before {{
  content: counter(t, decimal-leading-zero); position: absolute; left: -13px; top: 1px;
  width: 26px; height: 26px; border-radius: 4px; background: var(--bg1);
  border: 1px solid var(--separator2); color: var(--fg3); font-family: {MONO};
  font-size: 11px; display: grid; place-items: center;
}}
ol.trail li .what {{ font-weight: 600; color: var(--fg0); display: block; margin-bottom: 2px; }}
ol.trail li .how {{ color: var(--fg2); font-size: 15px; }}

ul.spec {{ margin: 4px 0 0; padding-left: 22px; }}
ul.spec li {{ margin-bottom: 9px; color: var(--fg2); }}
ul.limits {{ list-style: none; margin: 22px 0 0; padding: 0; }}
ul.limits li {{
  padding: 14px 0 14px 30px; border-bottom: 1px solid var(--separator1);
  position: relative; color: var(--fg2); font-size: 15px;
}}
ul.limits li:last-child {{ border-bottom: none; }}
ul.limits li::before {{
  content: ""; position: absolute; left: 6px; top: 23px; width: 8px; height: 8px;
  background: var(--fgModerate);
}}

.item {{ display: grid; grid-template-columns: 1fr 200px; gap: 8px 26px; padding: 17px 0; border-bottom: 1px solid var(--separator1); }}
.item:last-child {{ border-bottom: none; }}
.item .t {{ font-weight: 600; color: var(--fg0); }}
.item .d {{ color: var(--fg2); font-size: 15px; grid-column: 1; }}
.item .refs {{ grid-row: 1 / span 2; grid-column: 2; font-family: {MONO}; font-size: 12.5px; color: var(--fg3); text-align: right; }}
@media (max-width: 720px) {{
  .wrap {{ padding: 0 16px 96px; }}
  .mast::before {{ inset: 0 -16px; }}
  .panel {{ padding: 20px 16px 18px; }}
  .item {{ grid-template-columns: 1fr; }}
  .item .refs {{ grid-row: auto; grid-column: 1; text-align: left; }}
}}

.foot {{
  margin-top: 88px; padding-top: 28px; border-top: 1px solid var(--separator1);
  font-size: 14px; color: var(--fg3); display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 26px;
}}
.foot .k {{
  font-family: {MONO}; font-size: 11px; letter-spacing: .05em;
  text-transform: uppercase; color: var(--fg4); display: block; margin-bottom: 6px;
}}
.foot code {{ background: none; padding: 0; font-size: 13px; color: var(--fg2); }}
.foot .logo {{ color: var(--fg3); }}
"""


# ------------------------------------------------------------------------ formatting
# LiveKit's writing rules (bytes-react Writing.mdx): numerals with a non-breaking
# space before the unit, thousands separated by commas, K/M with no space.
NBSP = "&#160;"


def num(v, d=0) -> str:
    """2267 -> '2,267'."""
    return f"{v:,.{d}f}"


def compact(v, d=1) -> str:
    """17600 -> '17.6K', 2.4e6 -> '2.4M'. No space between number and letter."""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return f"{v / div:.{d}f}".rstrip("0").rstrip(".") + suf
    return f"{v:g}"


def q(v, unit, d=0) -> str:
    """A number and its unit, joined by a non-breaking space: q(240, 'ms')."""
    return f"{num(v, d)}{NBSP}{unit}"


# ---------------------------------------------------------------------- statistics
def pct(xs, f):
    """Linear-interpolated percentile, the convention numpy and dashboards use."""
    xs = sorted(xs)
    i = f * (len(xs) - 1)
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (i - lo) * (xs[hi] - xs[lo])


def describe(xs):
    xs = sorted(xs)
    q4 = st.quantiles(xs, n=4)
    sd = st.stdev(xs) if len(xs) > 1 else 0.0
    mean = st.mean(xs)
    return dict(n=len(xs), lo=xs[0], hi=xs[-1], mean=mean, med=st.median(xs), sd=sd,
                q1=q4[0], q3=q4[2], iqr=q4[2] - q4[0], p90=pct(xs, .90), p95=pct(xs, .95),
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


def key(items) -> str:
    """An HTML legend. items: [(label, token)], e.g. [("baseline", "data-a")]."""
    return '<div class="key">' + "".join(
        f'<span><i style="background:var(--{t})"></i>{lab}</span>' for lab, t in items) + "</div>"


def bar_compare(rows, unit="ms", label="comparison", top=None, ratio_note=True):
    """Means on one axis with min-max whiskers. rows: [(name, describe(), 'a'|'b')].

    The headline comparison chart. Whiskers are the observed range, not error bars,
    and the caption should say so.
    """
    w, h = 1000, 60 + 70 * len(rows) + 60
    x0, x1 = 150, 880  # room right of the longest whisker for its value label
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
        s.append(f'<rect class="bar-{cls}" x="{x0}" y="{y}" width="{x(d["mean"]) - x0:.1f}" height="{bh}" rx="2"/>')
        s.append(f'<line class="whisk" x1="{x(d["lo"]):.1f}" y1="{y + bh / 2}" x2="{x(d["hi"]):.1f}" y2="{y + bh / 2}"/>')
        for v in (d["lo"], d["hi"]):
            s.append(f'<line class="whisk" x1="{x(v):.1f}" y1="{y + 10}" x2="{x(v):.1f}" y2="{y + bh - 10}"/>')
        s.append(f'<text class="rowlab" x="{x0 - 16}" y="{y + bh / 2 + 5}" text-anchor="end">{name}</text>')
        s.append(f'<text class="val val-{cls}" x="{x(max(d["mean"], d["hi"])) + 14:.1f}" y="{y + bh / 2 + 6}">'
                 f'{num(d["mean"])}{NBSP}{unit}</text>')
        ends.append(x(d["mean"]))
    if ratio_note and len(rows) == 2:
        a, b = rows[0][1]["mean"], rows[1][1]["mean"]
        xa, xb = min(ends), max(ends)
        ym = 60 + 70 - 12
        s.append(f'<path class="brace" d="M {xa:.1f} {ym + 8} L {xa:.1f} {ym} L {xb:.1f} {ym} L {xb:.1f} {ym + 8}"/>')
        s.append(f'<text class="ratio" x="{(xa + xb) / 2:.1f}" y="{ym - 8}" text-anchor="middle">'
                 f'&#8722;{num(abs(a - b))}{NBSP}{unit} &#183; {max(a, b) / min(a, b):.2f}&#215;</text>')
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
             f'text-anchor="middle">median {num(d["med"])}</text>')
    s.append("</svg>")
    return "\n".join(s)


_SEG_CYCLE = ("chart1", "chart2", "chart3", "chartNeutral")


def stacked(parts, unit="ms", label="decomposition", total_note=""):
    """One bar split by owner. parts: [(name, value, note)] or [(name, value, note, colour)].

    `colour` is a pipeline stage key ('llm', 'stt', 'tts', 'tool', 'eou', 'realtime')
    or any token name; without it segments cycle chart1, chart2, chart3, chartNeutral.
    Use stage keys for agent latency so a stage has the same colour as in LiveKit's
    own dashboards. If a part is a residual rather than a measurement, say so in its note.
    """
    total = sum(p[1] for p in parts)
    w, h = 1000, 190
    x0, x1 = 20, 980
    x = x0
    s = [_svg(w, h, label)]
    for i, p in enumerate(parts):
        name, v, note = p[:3]
        tok = p[3] if len(p) > 3 else _SEG_CYCLE[i % len(_SEG_CYCLE)]
        tok = STAGES.get(tok, tok)
        bw = (v / total) * (x1 - x0)
        tx = x + bw / 2
        s.append(f'<rect class="seg" style="fill:var(--{tok})" x="{x:.1f}" y="30" width="{bw:.1f}" height="52" rx="2"/>')
        s.append(f'<text class="seglab" style="fill:var(--on-{tok})" x="{tx:.1f}" y="62" '
                 f'text-anchor="middle">{v:g}{NBSP}{unit}</text>')
        s.append(f'<text class="segname" x="{tx:.1f}" y="104" text-anchor="middle">{name}</text>')
        s.append(f'<text class="segnote" x="{tx:.1f}" y="124" text-anchor="middle">{note}</text>')
        x += bw
    s.append(f'<text class="segtotal" x="{x1}" y="164" text-anchor="end">'
             f'{total:g}{NBSP}{unit}{" &#183; " + total_note if total_note else ""}</text>')
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
        s.append(f'<text class="phval" x="{x0 + bw + 12:.1f}" y="{y + 16}">{v:g}{NBSP}{unit}</text>')
        if note:
            s.append(f'<text class="phcount" x="{w - 10}" y="{y + 16}" text-anchor="end">{note}</text>')

    for i, (name, v, note) in enumerate(head_rows):
        emit(i, name, v, note, top_head, "hot")
    off = len(head_rows)
    if split:
        yb = 24 + off * rowh + 12
        s.append(f'<line class="phbreak" x1="{x0 - 200}" y1="{yb}" x2="{w - 10}" y2="{yb}"/>')
        s.append(f'<text class="phscale" x="{x0 - 14}" y="{yb + 15}" text-anchor="end">'
                 f'BELOW, SCALE &#215;{top_head / top_tail:.0f}</text>')
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


def color(token, theme="dark"):
    """A token's hex for one theme, for contrast checks: color('fg3', 'light')."""
    token = ROLES.get(token, token)
    return TOKENS[token][0 if theme == "dark" else 1]


def validate(html, strict=True):
    """The checks that catch the mistakes that actually happen. Returns a problem list.

    1. A token used but not defined in the bare `:root` renders nothing in the
       default (dark) state for every viewer. `var(--x, fallback)` is exempt: that is
       a local property such as `.decor`'s `--c`.
    2. Unbalanced containers silently swallow the rest of the page.
    3. SVG content outside its own viewBox is invisible or clipped.
    4. A doctype/html/body wrapper is added at publish time; including one nests.
    5. More than one `.hl` accent highlight breaks Bytes' one-accent-per-screen rule.
    """
    problems = []
    m = re.search(r":root\s*\{(.*?)\n\}", html, re.S)
    if not m:
        problems.append("no bare :root block: the dark palette has nowhere to live")
    else:
        defined = set(re.findall(r"(--[\w-]+)\s*:", m.group(1)))
        used = set(re.findall(r"var\((--[\w-]+)\s*\)", html))
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
        ys = [float(v) for v in re.findall(r'\sc?y="([-\d.]+)"', body)]
        out = [v for v in ys if v < -2 or v > vh + 2]
        if out:
            problems.append(f"{len(out)} SVG y-coords outside a viewBox of height {vh:g}")
    if re.search(r"<!doctype|<html[\s>]|<body[\s>]", html, re.I):
        problems.append("remove <!doctype>/<html>/<body>: the publisher adds the skeleton")
    if "background" not in html:
        problems.append("body needs an explicit background from a token, or it "
                        "borrows the host's theme")
    if len(re.findall(r'<span class="hl"', html)) > 1:
        problems.append("more than one .hl accent highlight: Bytes reserves the accent "
                        "for one emphasis per screen")
    if strict and problems:
        raise SystemExit("brand.validate failed:\n  " + "\n  ".join(problems))
    return problems


# ---------------------------------------------------------------------- source sync
def check(web_root: str) -> int:
    """Diff TOKENS against a `livekit/web` checkout. Returns the number of mismatches."""
    cdir = os.path.join(web_root, "packages", "bytes-core", "colors")
    raw_src = open(os.path.join(cdir, "raw-colors.ts")).read()
    two_src = open(os.path.join(cdir, "two-face-colors.ts")).read()
    raw = {"white": "#FFFFFF", "black": "#000000"}
    for scale, body in re.findall(r"'?([\w-]+)'?:\s*\{([^}]*)\}", raw_src):
        for step, hx in re.findall(r"(\d+):\s*'(#[0-9A-Fa-f]{6})'", body):
            raw[f"{scale}.{step}"] = hx.upper()

    def ref(expr):
        mm = re.match(r"rawColors(?:\.(\w+)|\['([\w-]+)'\])(?:\['(\d+)'\])?", expr.strip())
        if not mm:
            return None
        scale = mm.group(1) or mm.group(2)
        return raw.get(f"{scale}.{mm.group(3)}" if mm.group(3) else scale)

    src = {}
    for mm in re.finditer(r"(\w+):\s*\{\s*(?://[^\n]*\n\s*)?light:\s*([^,]+),\s*dark:\s*([^,]+),",
                          two_src):
        src[mm.group(1)] = (ref(mm.group(3)), ref(mm.group(2)))
    for mm in re.finditer(r"(\w+):\s*semanticColors\.(\w+),", two_src):
        if mm.group(2) in src:
            src[mm.group(1)] = src[mm.group(2)]
    bad = 0
    for k, (d, l) in TOKENS.items():
        if k not in src:
            print(f"  {k}: not in two-face-colors.ts (renamed or removed?)")
            bad += 1
        elif (d.upper(), l.upper()) != src[k]:
            print(f"  {k}: brand.py {d}/{l}  web {src[k][0]}/{src[k][1]}")
            bad += 1
    print(f"{len(TOKENS)} tokens checked, {bad} mismatched")
    return bad


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(1 if check(sys.argv[2]) else 0)
    print("usage: brand.py --check <path to livekit/web checkout>")
