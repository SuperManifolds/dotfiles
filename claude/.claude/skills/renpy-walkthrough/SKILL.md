---
name: renpy-walkthrough
description: Build an in-game walkthrough patch for a Ren'Py visual novel - a drop-in walkthrough.rpy that adds green ▲ / red ▼ / grey ● hint lines under the game's own menu choices, menu-wide notes, hints on typed prompts and a W toggle - by inventorying every choice through the game's own engine, analyzing what each choice changes, and verifying the patch headlessly and visually. Use when asked for a "walkthrough patch", "walkthrough mod", "in-game walkthrough" or "choice hints" for a Ren'Py game, or "which choices are best in <VN>" when the game is on disk. Works on .app, folder, .sh or .zip builds, Ren'Py 7 (Python 2) and 8, games that ship scripts only as .rpyc inside .rpa archives, and custom list-based choice screens.
allowed-tools:
  - Bash(python3 -I ~/.claude/skills/renpy-walkthrough/rpw.py:*)
  - Read
  - Write
  - Edit
---

# renpy-walkthrough

One stdlib helper does the mechanical work; you do the analysis. Always run it spelled out as
`python3 -I ~/.claude/skills/renpy-walkthrough/rpw.py <cmd>` (that form matches this skill's
allowed-tools, so it runs without a permission prompt; subagents use it too). Every shell call
starts fresh, so aliases, functions and variables don't carry over; below, `rpw.py <cmd>` is
short for that full command.
Tested on macOS. Linux uses the same code without `open -g` (untested); on Windows the
analysis commands load, but launching games (dump, verify, preview) is untested. Per-game state lives in a work dir, `~/renpy-walkthroughs/<slug>/`; any rpw command
accepts the slug instead of the full path. Keep scratch files inside the work dir:
the session scratchpad is shared with parallel agents.

## Flow

1. **Dump.** `rpw.py dump <game> [--work DIR]` (locates the game first; a `.zip` is
   unpacked next to itself). It copies `assets/_rpw_dump.rpy` into `game/`, runs the
   engine's headless lint (no audio, one run per game at a time), and removes the file.
   Output in the work dir:
   - `rpw_dump.json`: menus with conditions, an outline of each item and of what runs
     right after the menu, the reads index (`if`/`while`/menu conditions, Python),
     `define`/`default` statements, typed prompts, call/show-screen sites, labels with
     dialogue counts, screens;
   - `pseudo/`: Ren'Py-like source rebuilt from the AST, line numbers matching the
     original; `show --source` uses it when no `.rpy` exists;
   - `lint-baseline.txt`.
   Re-run `dump` whenever rpw warns that the dump is older than the dumper.
2. **Extract**: `dump` also runs `rpw.py extract DIR`, which copies every script into
   `DIR/src/` (`.rpa` contents and loose `.rpy`/`.rpyc`). `show --source`, gallery detection
   and the screen-read search need it; run it by hand only if `src/` is missing.
3. **Recon.** `rpw.py recon DIR`. Verdicts:
   - `menu-driven`: continue.
   - `mixed`: continue. Choices made of image-button screens, timers or free-roam maps
     can't get per-button hints, but a `SCREEN_NOTES` entry shows a note while that
     `call screen` waits (see `reference/hints-format.md`); `renpy.display_menu` gets nothing.
   - `custom-choice-system`: the game calls its own choice screen with a list of
     choice objects (`call screen choicescreen("m1choice1")`). Configure `LIST_SCREENS`
     (see `reference/hints-format.md`) and hint `@listname` keys. If the screen takes
     something else, explain the limits and offer a written walkthrough instead.
   - `tune mode suggested`: fixed-size buttons; follow `reference/tune-mode.md`.
   - `width: ... fits about N characters`: put `HINT_MAX_LEN = N` in `hints.py`.
   - `story: ... unreached: label X`: the story graph can't see how the game gets there
     (usually a screen button); find the statement that leads there and add `FLOW_EDGES`
     (see `reference/hints-format.md`) so `budget` counts the right paths.
4. **Confirm scope** with the user (chapters, and whether to also publish a written
   walkthrough page). Skip the question for small games (under ~50 menus): cover all.
   If the game ships its own walkthrough or hint colouring, ignore it and work from the code.
5. **Analyze.** Read `reference/rubric.md` and `reference/analysis-traps.md` first. Per menu:
   `rpw.py show DIR FILE:LINE --source 40` (or `show DIR @listname`) prints each item's
   outline with `<==` assignments, gallery unlocks and scenes, jump targets with their
   dialogue counts, loop-backs, the after-menu block, and every read of each assigned
   variable grouped by file. `rpw.py budget DIR VAR` lists the starting value, all changes and
   threshold reads of a points variable with the choice each change belongs to, and marks
   changes no story read can follow; for method-based systems pass a regex
   (`budget DIR 'Miya\.(points|pointch)|pointcheck\(Miya'`). `--before FILE:LINE` gives the
   range reachable at a threshold along story paths (exclusive branches don't add up, flag
   conditions are followed and the range is split by the flags that decide it);
   `--via FILE:LINE` limits it to paths through one choice's statement, which answers "does
   this pick decide the check?"; `--gain 'Miya\.pointch\((-?\d+)'` sums method-based gains.
   For list screens, `show DIR @name` prints each target label's effects.
   `rpw.py list DIR [--group]` is the inventory (header row explains the columns;
   `--group` collapses copy-pasted menus). Menus flagged `replay-only` or
   `single-option` need nothing.
   For more than ~40 menus, fan out one general-purpose Agent per group of files. Each
   writes only `DIR/hints.d/<part>.py` and validates with `check DIR --only 'GLOBS'`;
   only the coordinator runs `dump`, `gen`, `verify`, `preview` (ignore stale-dump warnings
   while agents are working; the coordinator re-dumps and re-checks afterwards).
6. **Write `DIR/hints.py`** (format: `reference/hints-format.md`).
7. **Generate and check.** `rpw.py gen DIR`, `rpw.py check DIR` (must end
   `0 errors, 0 gaps`; fix warnings).
8. **Verify.** `rpw.py verify DIR --negative` must print `PASS`. It checks:
   - the engine self-check reports `N entries, 0 mismatches`, with no new lint findings;
   - a corrupted caption is detected;
   - an injected start-up error leaves the game running with the patch off;
   - in one background game run:
     - the most demanding hinted menu renders;
     - the 3 tallest hinted menus plus the one with the longest hint keep every choice on
       screen with hints on (`fit:`);
     - an injected runtime error only hides the hints;
     - a screen note renders.
   A `fit:` failure means hints push choices off screen: shorten them or set
   `PATCH_DEFINES = {"wt_long_menu_shift": 1.0, "wt_long_menu_from": 1}` (the second key lifts
   menus with fewer than 6 choices too). For any other failure, read `reference/engine-notes.md`. A `fit:` warning ("hint(s) wrap") is measured
   from the real buttons: shorten those hints or lower `HINT_MAX_LEN`.
9. **Look at it.** `rpw.py preview DIR FILE:LINE|@list [--setup "python"]` boots the game in
   the background (on macOS through `open -g`, window moved off screen, no focus taken),
   shows that menu (or `call screen` site) with hints and saves a PNG; Read it.
   Preview one plain menu, one with a note, one with long captions, one with a greyed
   (conditional) item, and one of each special style (pass the variable the game sets before
   them via `--setup`). Menus the game shows with another screen (`menu (screen="phone")`,
   NVL) get no item hints; `recon` and `check` name them. Typed names get their defaults automatically.
9b. **Spot-check.** `rpw.py spotcheck DIR --sample 10` writes `DIR/spotcheck/brief.md`: give it to
    a fresh general-purpose Agent (it re-derives those hints blind, without seeing ours).
    `rpw.py spotcheck DIR --compare` grades its answer per choice. For every `conflict`,
    `missed` or `overclaim`, read the code and fix whichever side is wrong; then `gen` and
    `verify` again. Several fixes in one game mean the sample found a pattern: widen it.
10. **Install and hand over.** `rpw.py install DIR`, then `rpw.py readme DIR --notes "..."`
    (coverage, what can't be hinted, commands; the notes carry the main payoffs and
    thresholds) and tell the user: W (or clicking the "Walkthrough" label) toggles hints, `rpw.py uninstall DIR` removes them.
    Publish the written walkthrough with the Artifact tool if they asked for one.

## After a game update

`rpw.py update DIR` (once the new version is in place, same path):
1. It uninstalls the patch, re-dumps (keeping the old dump as `rpw_dump.prev.json`), re-runs
   `extract`, and runs `migrate --write`, so hints whose menus only moved get their new line.
2. It stops when `migrate` reports `lost` menus (text changed or ambiguous) or `recheck` lines
   ("not used yet" hints whose variable gained a read), or when `check` reports gaps or errors.
   `check` also errors on any hinted menu that differs from the one `walkthrough.rpy` was made
   for. Re-analyse those (`show`), fix `hints.py`, then run `gen` (which records the new menus),
   `check`, `verify --negative` and `install`.
3. Otherwise it continues with `gen`, `verify --negative` and `install`.
4. Tune mode: compare the game's new `screen choice` with `DIR/screen_choice.rpy` first.

## Stop and ask when

- recon says `custom-choice-system` and the screen does not take a list of objects;
- `verify` fails and the cause is not a typo in `hints.py`;
- the self-check wraps nothing (`wrapped {'choice': []}`);
- a choice's effect depends on state you cannot trace: hint only what the code shows.

## Rules

- Code wins over community guides and over the game's own hint colouring.
- Hints name the kind of payoff (gallery scene, route kept or lost, correct answer,
  Trust +2), never plot.
- Never edit the game's own files. The patch is one added file; `uninstall` restores the game.
- References: `reference/rubric.md` and `reference/analysis-traps.md` (step 5),
  `reference/hints-format.md` (writing hints), `reference/engine-notes.md` (when recon,
  verify or preview reports a problem), `reference/tune-mode.md` (fixed-size buttons).
