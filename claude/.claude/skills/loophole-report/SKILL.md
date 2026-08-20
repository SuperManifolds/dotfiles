---
name: loophole-report
description: Build a Loophole Labs branded HTML report from measurements or findings and publish it as an Artifact, with charts generated from the data. Use when the user asks for a report, writeup, or shareable page about engineering work, benchmarks, or an investigation.
argument-hint: "[subject, and where the data lives]"
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Artifact, Skill
---

Produce a report page in the house style for `$ARGUMENTS`, publish it as an Artifact,
and keep the generator next to the work so it can be regenerated.

This skill is about reports whose spine is **evidence**: a benchmark, an
investigation, a postmortem, an audit, a design decision with measurements behind
it. For a page that is mostly prose or mostly UI, use the `artifact-design` skill on
its own instead.

## Before anything

Run `Skill(artifact-design)` first. It calibrates how much design a request warrants
and its rules on themes and titles apply here too. This skill is the Loophole-specific
layer on top: the palette is fixed, the type is fixed, and the editorial standards
below are the part that makes a report worth reading.

## Steps

1. **Find the data and the audience.** Two questions decide the whole page: what
   measurement or finding is the spine, and who reads it. Locate the raw numbers
   (a CSV, a log, a test output) rather than working from a summary someone typed.
   If the numbers only exist in a scratch directory, that is a problem to fix in
   step 6, not to paper over.

2. **Read the brand palette from source, not memory.** The truth is
   `design/src/styles/colors.css` in the architect monorepo. `brand.py` beside this
   file carries the conversions; if the CSS has moved on, update `brand.py` and say
   so. The identity in one line: Loophole purple `#7242FF` for structure and links,
   the deep purple `#0B081C` ground in dark mode, and **`--color-text-architect`
   `#D84922`** as the data accent for anything in the architect/cruise world. Green
   `#31D822` and red `#DF0101` are semantic and stay separate from the accent.

3. **Write a generator, not markup.** Create `<name>-report.py` next to where the
   report will live. Data goes in arrays at the top; the script emits one
   self-contained HTML file. Never hand-type a number into markup: every chart
   coordinate and every table cell is computed, so the page cannot drift from the
   data. Import the toolkit:

   ```python
   import sys, os
   sys.path.insert(0, os.path.expanduser("~/.claude/skills/loophole-report"))
   import brand

   COLD = [7276, 7325, ...]        # the raw samples, in collection order
   C = brand.describe(COLD)        # n, min, max, mean, med, sd, iqr, p90, p95, cv

   html = (brand.head("Queue Latency")
           + f"<style>{brand.css()}</style>"
           + '<div class="wrap">' + body + '</div>')
   brand.validate(html)            # raises on the mistakes that actually happen
   open(OUT, "w").write(html)
   ```

   Paths in the generator must be derived from `__file__`, never absolute, or it only
   works on your machine.

4. **Pick charts that carry an argument.** `brand.py` provides
   `bar_compare` (means with min-max whiskers, the headline comparison),
   `beeswarm` (every sample, displaced only where dots collide, so height is density
   and never collection order), `stacked` (one figure split by owner, to stop a
   headline being read as one component's cost), `hbars` (ranked breakdown, with a
   `split` that magnifies a long tail), `dot_matrix` (pass/fail as dots, so the
   reader sees the n), and `series` (value against index, to show a run does not
   drift). Also `welch` and `mann_whitney` for the comparison, which need no scipy.

   Every chart gets a `figcaption` naming what it shows and a `chartnote` saying what
   it does **not**: whiskers that are ranges rather than error bars, widths that are
   not comparable across a scale break, a vertical axis that carries no meaning.

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
   - **Plain section titles.** "Root cause: systrap syscall patching", not "The
     blocker was not ours". No hero flourishes, no "turned out to be", no
     self-congratulation. The finding is the interesting part.
   - **Link tickets and PRs inline**, and write "no ticket yet" rather than linking
     something adjacent. Linear is `https://linear.app/loopholelabs/issue/ARCH-nnnn`,
     GitHub is `https://github.com/loopholelabs/architect/pull/nnnn`. Look up real
     titles and statuses with the Linear tools rather than guessing.
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
   balance, SVG bounds and the doctype mistake. Then check by hand:

   ```
   grep -c '—' report.html          # em dashes: rewrite the clause, do not swap the glyph
   python3 -c "...contrast..."      # brand.contrast(fg, bg) >= 4.5 for body type
   ```

   Publish with the `Artifact` tool. Title is a short, specific noun phrase with no
   appended explainer; the one-sentence `description` is where the explanation goes.
   Pick a favicon and **keep it stable across redeploys**. Republishing the same file
   path keeps the URL. Artifacts are private until the user shares them, so say that
   when you hand over the link.

8. **Review your own page before handing it over.** Read it as a reviewer who wants
   to find an error, and check the arithmetic in every derived figure: parts that
   should sum to a total, ratios, counts that appear in more than one place. Both
   errors found in the report this skill came from were of exactly that kind, and
   both were in the summary rather than the detail. Then offer the user a list of
   what would improve it, separating what you can do now from what needs new
   measurement.

## Things that will bite

- **Fonts.** Inter is the brand sans and is Google-hosted, so it links. Commit Mono
  is the brand mono and is **not** on Google Fonts: `brand.find_brand_font()` looks
  for `design/src/fonts/commit-mono-variable.woff2` in a monorepo checkout above the
  working directory and inlines it as a data URI. Its weight axis stops at 500, so
  never ask for 700 on mono type or you get a synthesised faux-bold.
- **The artifact CSP** admits no host but Google Fonts. Inline everything else as a
  data URI. No CDN scripts, no remote images.
- **Themes have three states**, not two: an explicit choice stamps the root element,
  and the default "system" setting stamps nothing. `brand.css()` handles it, but if
  you add a colour, add it to the bare `:root` too or it will not apply for most
  viewers.
- **Wide content needs its own `overflow-x: auto`** container, which is what
  `.scroller` is for. The page body must never scroll sideways.
