# Classifying a choice

Work down the ladder; the first rung that applies decides the hint.

| # | What the code shows | Hint |
|---|---|---|
| 1 | A route flag set or cleared, read later in `if` conditions (or never read yet, but the game's own note calls it an opt-in) | good "Keeps X's route" / bad "Locks X's route"; add the payoff when countable, "(2 scenes)" |
| 2 | A gallery scene: `<== GALLERY scene` (jump/call/label is a replay label), `<== GALLERY unlock` (a persistent flag the gallery reads), or a label inside the item that the gallery lists | good "Gallery scene" / "Unlocks a gallery picture"; bad "Skips a gallery scene" on the alternative |
| 3 | A stat that a later **condition** reads (never count dialogue mentions or `[var]` display) | good "Trust +3" when it matters; follow the read (`budget VAR`) to say what it gates and whether every point is needed |
| 4 | A scored quiz or puzzle (`score += 1` on one answer) | good "Correct answer"; note on the first question about the reward; for a menu that only picks which question comes next: "Either question leads to one scored guess" |
| 5 | Loop menu (items set a visited flag and jump back) | note "Ask/visit all N (any order) before ..."; good on items with payoffs; bad on an early exit only when it can be taken before the rest are done. Navigation dead ends (a line or two, then `(loops back above the menu)`): info "Loops back" on them, good "The way on" on the exit, not "ANY" |
| 6 | Combination puzzle (several menus feed one score with thresholds) | compute the best combination in Python, same operation order as the game; note "Best: A, B, C" on each menu; good on the matching items |
| 7 | One branch is much longer: compare `say=` counts, jump targets' counts, and the after-menu block (flags set in the item often branch right after the menu) | good "Extra scene" / "Extra dialogue" |
| 8 | Death or bad ending that loops back to the menu (`(loops back above the menu)`), possibly counting toward an achievement | bad "Game over, retry" (or info "Death: counts toward an achievement") |
| 8b | Mistake counters (`ericFight += 1`, then `>= 2` loses): the incrementing items are the bad ones | bad "Wrong move (2 lose the fight)"; good on the right move |
| 9 | Content preference toggles (turn a fetish off for good) | note "Content setting: ..." with no judgement |
| 10 | Equal-weight paths or tone/trait picks (friendly/witty/aggressive, maledom/femdom) | info hints ("Friendly +1") or one note describing the items by position |
| 11 | Stats set but never read in this build (episodic games) | info "X +1 (not used yet)"; also when a stat is only shown on a stats screen |
| 12 | Values exported to a sequel (`MultiPersistent`, `persistent.<name>` read by the sequel) | read the sequel's conditions; "Carries into Part 2: X's path" |
| 13 | Name pickers, cosmetic flags that only swap lines | note "Cosmetic: ..." |
| 14 | Nothing measurable | `"ANY"` |

## Evidence habits

- `rpw.py show DIR FILE:LINE --source 40` for every menu; read the source around each
  read site before naming a payoff. Check the after-menu block.
- `rpw.py budget DIR VAR` for every points variable: it lists the starting value
  (`define`/`default`), every `+=`/`-=` with the choice it belongs to, and every threshold.
  Work out the maximum reachable before each threshold; when every point is needed, say so
  in the note ("needs all 4 of Nora's points").
- Reads that live only in screens (stat screens, phone UIs) are not in the dump; grep
  `DIR/src` with `grep -rn` (subfolders like `bin/scripts/` matter).
- `budget VAR --before FILE:LINE` gives the range reachable before a threshold along story
  paths; add `--via FILE:LINE` (a statement inside one choice) to see whether that pick decides
  it. Before writing "needs every point", "not used yet" or "passes either way", run both:
  the claim holds only if the numbers say so (`check` warns when a "not used yet" stat is read
  later; `--via` with the low pick still passing means
  "passes either way"). The output splits by the flags that matter (`escort=0: 3 to 3`);
  conditions on numbers are not followed (see analysis-traps.md), so check those in the code.
- Greyed-out choices: `config.menu_include_disabled`, or item arguments such as
  `"Keep going." (enable=riley >= 5)` read by a custom choice screen (`list` shows them in
  the condition column and they are in the reads index): put the requirement in the hint
  ("Gallery (needs Miharu 7)"); the patch dims hints on disabled items.
- State-dependent answers (a maze whose correct turn depends on a variable) can't be one
  fixed hint: use a note with the rule.
- Image-button choices and timed QTE screens can't be hinted; list them in the README.
- The developer's own caption lines inside a menu are evidence, but confirm against the code.
- A choice that leads to a gallery scene AND a route flag gets both, joined with " · ".

## Phrasing

- Short, factual, no plot: "Gallery scene (darker in tone)", "Wrong · locks Millie's route".
- Good lines say what you gain; bad lines say what you lose; info lines just state the effect.
- Only mark the bad items that cost something. Leave neutral items blank.
- Notes for menu-wide advice: "Best profile: ...", "Visit all three places (any order) before leaving."

Worked examples from real games: `examples.md` (not for spot-check agents).
