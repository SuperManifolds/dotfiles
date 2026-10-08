---
name: livekit-report
description: Build a LiveKit branded HTML report from measurements or findings and publish it as an Artifact, with charts generated from the data. Use when the user asks for a report, writeup, or shareable page about engineering work, benchmarks, or an investigation.
argument-hint: "[subject, and where the data lives]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Artifact, Skill
---

Produce a report page in LiveKit's house style for `$ARGUMENTS`, publish it as an
Artifact, and keep the generator next to the work so it can be regenerated.

This skill is about reports whose spine is **evidence**: a benchmark, an
investigation, a postmortem, an audit, a design decision with measurements behind
it. For a page that is mostly prose or mostly UI, use the `artifact-design` skill on
its own instead.

## Before anything

Run `Skill(artifact-design)` first. It calibrates how much design a request warrants
and its rules on titles apply here too. Where it says to follow the viewer's system
theme, this skill overrides it: LiveKit pages are **dark by default**. This skill is
the LiveKit layer on top: the palette is fixed, the type is fixed, and the editorial
standards below are the part that makes a report worth reading.

## Steps

1. **Find the data and the audience.** Two questions decide the whole page: what
   measurement or finding is the spine, and who reads it. Locate the raw numbers
   (a CSV, a log, a test output) rather than working from a summary someone typed.
   If the numbers only exist in a scratch directory, that is a problem to fix in
   step 6, not to paper over.

2. **Know the brand, and check it against source.** LiveKit's design system is
   **Bytes**, in the private `livekit/web` monorepo: `DESIGN.md` at the root, tokens
   in `packages/bytes-core/colors/{raw-colors,two-face-colors}.ts`, type in
   `packages/bytes-core/src/fonts.ts`, usage rules in
   `packages/bytes-react/stories/foundations/{Colors,Typography,Writing}.mdx`.
   `brand.py` carries the tokens under their Bytes names. If a `web` checkout is to
   hand (or `gh repo clone livekit/web -- --depth 1 --filter=blob:none --sparse`
   then `git sparse-checkout set packages/bytes-core`), run
   `python3 brand.py --check <web>`; on a mismatch, update `TOKENS` and say so.

   The identity in a few lines:
   - **Neutrals carry the page.** `bg1` `#070707` ground, `fg1` `#CCCCCC` body,
     `fg0` white for headings and figures, `separator1` `#202020` hairlines. Light
     theme exists (`#FDFDFC` / `#3B3B3B`) but is opt-in.
   - **One accent per screen.** `accent` is cyan `#1FD5F9` in dark, blue `#002CF2`
     in light. Spend it once: the key words of the headline (`<span class="hl">`),
     and as the data colour for *our* series. `validate()` rejects a second `.hl`.
   - **Data colours are not brand colours.** Charts use `chart1`…`chart8` in series
     order; meaning is pinned to `chartSerious` / `chartSuccess` / `chartModerate`.
     The baseline series is `chartNeutral` (`data-a`), ours is `chart1` (`data-b`).
   - **Agent pipeline stages have their own colours**: pass `"llm"`, `"stt"`,
     `"tts"`, `"tool"`, `"eou"`, `"realtime"` as the fourth element of a `stacked`
     part, so a latency breakdown matches the Cloud dashboard. Never use them for
     success or warning, and never alias Realtime to LLM.
   - **Type:** Public Sans for body and UI; TWK Everett (display, light 300 for
     `h1`, 400 for `h2`) only at 30px and up; CommitMono for numbers, code, labels
     and the uppercase "mono caps" eyebrows and table headers.
   - **Shape:** small radii (2–8px), hairlines instead of shadows, the Bytes 3px
     dot pattern behind the masthead. Shadows are for overlays only.

3. **Write a generator, not markup.** Create `<name>-report.py` next to where the
   report will live. Data goes in arrays at the top; the script emits one
   self-contained HTML file. Never hand-type a number into markup: every chart
   coordinate and every table cell is computed, so the page cannot drift from the
   data. Import the toolkit:

   ```python
   import sys, os
   sys.path.insert(0, os.path.expanduser("~/.claude/skills/livekit-report"))
   import brand

   COLD = [7276, 7325, ...]        # the raw samples, in collection order
   C = brand.describe(COLD)        # n, lo, hi, mean, med, sd, iqr, p90, p95, cv

   mast = (f'<header class="mast">{brand.logo()}'
           '<div class="eyebrow">Virtualization <span class="sep">/</span> Benchmark</div>'
           '<h1>Restore is <span class="hl">3.1× faster</span> with page prefetch</h1>'
           '<p class="standfirst">…</p></header>')
   html = (brand.head("Restore Latency")
           + f"<style>{brand.css()}</style>"
           + '<div class="wrap">' + mast + body + '</div>')
   brand.validate(html)            # raises on the mistakes that actually happen
   open(OUT, "w").write(html)
   ```

   Paths in the generator must be derived from `__file__`, never absolute, or it only
   works on your machine. Format numbers with `brand.num` (thousands commas),
   `brand.compact` (`17.6K`) and `brand.q(v, "ms")` (non-breaking space before the
   unit) rather than f-strings.

4. **Pick charts that carry an argument.** `brand.py` provides
   `bar_compare` (means with min-max whiskers, the headline comparison),
   `beeswarm` (every sample, displaced only where dots collide, so height is density
   and never collection order), `stacked` (one figure split by owner or pipeline
   stage, to stop a headline being read as one component's cost), `hbars` (ranked
   breakdown, with a `split` that magnifies a long tail), `dot_matrix` (pass/fail as
   dots, so the reader sees the n), and `series` (value against index, to show a run
   does not drift). `key()` builds an HTML legend from token names. Also `welch` and
   `mann_whitney` for the comparison, which need no scipy.

   Every chart gets a `figcaption` naming what it shows and a `chartnote` saying what
   it does **not**: whiskers that are ranges rather than error bars, widths that are
   not comparable across a scale break, a vertical axis that carries no meaning.

   Other components in `brand.css()`: `.figs`/`.fig` headline numbers on a hairline
   grid, `.badge.{ok,warn,bad,muted}` (mono caps, Bytes Badge), `.decor` with
   `style="--c:var(--fgLLM)"` (Bytes ValueDecorator, a coloured bar beside a label),
   `ol.trail`, `ul.limits`, `.item`, `pre` (`<b>` for highlighted, `<i>` for dimmed),
   `.foot`.

5. **Hold the line on these, because they are what separates a report from a pitch.**

   - **Label every number by how it was obtained.** Measured, computed, or residual.
     A residual carries the error of everything it was subtracted from, and calling
     it a measurement is the easiest way to mislead a reader who trusts you.
   - **State n, and the spread.** A mean alone is a claim without evidence. Ratios go
     on means and say so, especially when the arms are independent rather than paired.
   - **A limits section is mandatory.** What the numbers do not establish: asymmetric
     arms, one host, one workload, an n of 1 hiding inside a decomposition. Write it
     even when nobody asked, because the reviewer who finds an unstated limit stops
     trusting the stated ones.
   - **Name the failure modes you did not cover** where the work touches anything
     that could bite in production.
   - **Say where a number came from** at the point you report it: machine, kernel,
     versions, commit. Not as a description of your setup, which transfers to nobody,
     but as what a reader needs to interpret the figure.
   - **If a measurement method had an artifact, say so next to the numbers it
     affected**, and be precise about what survives: comparisons usually survive an
     artifact that hits both arms equally, absolute values usually do not.
   - **Plain section titles, in sentence case, without a trailing period.** "Root
     cause: systrap syscall patching", not "The blocker was not ours". No hero
     flourishes, no "turned out to be", no self-congratulation. The finding is the
     interesting part.
   - **Follow LiveKit's writing rules** (`Writing.mdx`): numerals not words; a
     non-breaking space between number and unit; `17.6K` with no space; `2,267` with
     a comma; en dash with no spaces for ranges (`4–6 ms`); curly quotes; `&` only in
     titles and labels, "and" in prose. Never "easy", "quick", "simply" or "just".
     No emoji.
   - **Link tickets and PRs inline**, and write "no ticket yet" rather than linking
     something adjacent. Linear is `https://linear.app/livekit/issue/VIRT-nnnn`,
     GitHub is `https://github.com/livekit/virtualization/pull/nnnn`. Look up real
     titles, statuses and the workspace URL with the Linear tools rather than
     guessing.
   - **Numbered section markers only when the content is a sequence.** An
     investigation's eliminations are a sequence: each one's failure motivated the
     next, so `ol.trail` is right. A catalogue of defects is not.

6. **Commit the generator and the data with the report.** A published page whose
   generator lives in a scratch directory cannot be regenerated by anyone else. Put
   the generator, and any collection scripts, in the repo next to the report, with a
   README saying where each one runs and whether it runs in CI. If a script carries
   fake credentials or a blackholed endpoint, say so in a comment before it becomes
   public.

7. **Validate, then publish.** `brand.validate()` covers the token audit, container
   balance, SVG bounds, the doctype mistake and the single-accent rule. Then check
   by hand:

   ```
   grep -c '—' report.html          # em dashes: rewrite the clause, do not swap the glyph
   python3 -c "...contrast..."      # brand.contrast(brand.color('fg3'), brand.color('bg1')) >= 4.5
   ```

   Check contrast in both themes (`brand.color(tok, "light")`) for any colour you
   introduce. Publish with the `Artifact` tool. Title is a short, specific noun phrase
   with no appended explainer; the one-sentence `description` is where the
   explanation goes. Pick an icon and **keep it stable across redeploys**.
   Republishing the same file path keeps the URL. Artifacts are private until the
   user shares them, so say that when you hand over the link.

8. **Review your own page before handing it over.** Read it as a reviewer who wants
   to find an error, and check the arithmetic in every derived figure: parts that
   should sum to a total, ratios, counts that appear in more than one place. Errors
   of that kind cluster in the summary rather than the detail. Then offer the user a
   list of what would improve it, separating what you can do now from what needs new
   measurement.

## Things that will bite

- **Fonts.** Public Sans links from Google Fonts. CommitMono and TWK Everett are
  inlined from `fonts/` beside this file. That directory is gitignored (the
  dotfiles repo is public and the fonts are licensed); `brand.py` fetches missing files
  from `livekit/web/apps/cloud/fonts` with `gh` on first use. `head()` embeds Everett 300 and 400 only; pass
  `display_weights=(300, 400, 600)` if a heading needs more, at ~75 KB each once
  base64 encoded. Everett is unreadable below 30px: never use it for body, labels or
  `h3`.
- **The artifact CSP** admits no host but Google Fonts. Inline everything else as a
  data URI. No CDN scripts, no remote images.
- **Themes.** The bare `:root` is the complete **dark** palette, and only an explicit
  `data-theme="light"` (or `data-lk-theme="light"`) switches to light; there is
  deliberately no `prefers-color-scheme` block. If you add a colour, add it to
  `TOKENS` with both values so it lands in both blocks.
- **Ink on chart fills.** Every chart and stage token gets an `--on-<token>` partner,
  near-black or white, whichever contrasts more with that fill in that theme. Use
  `fill:var(--on-chart2)` for a label on a `chart2` mark. A segment too narrow for its
  label needs the label moved out, not shrunk.
- **Highlighted table rows** are `tr.sel`, not `.hl`: `.hl` is the headline accent.
- **Wide content needs its own `overflow-x: auto`** container, which is what
  `.scroller` is for. The page body must never scroll sideways.
