# Analysis traps

Read before analysing menus (SKILL.md step 5): what the code shows and what it doesn't.

- **Reads**: a word-boundary grep for a variable matches English dialogue ("closer"). Only
  conditions and Python count; `show` and `budget` use the dump's reads index. `copy`
  reads (`cvar.trust = trust`) are exports, not gates.
- **Starting values**: games often `define` mutable stats with a non-zero start
  (`define s_aff = 4`); `budget` prints it.
- **Story graph (`rpw_cfg.json`)**: `dump` also exports the control flow of every statement.
  `budget` follows it from `start`: jumps, calls (a called label's gains are added where it
  returns), `set` menus that end once all items are picked, `call screen` buttons
  (`Jump("x")`, `Jump(var)` with the value set just above, `Jump("main" + str(n))`,
  `Function(f)` whose body jumps, label names in list arguments), `renpy.jump` in Python,
  `elif` clauses (anchored to their `if`), and optional side trips that come back: `Call("x")`
  buttons, `renpy.call` in Python, and label names passed to a `call` as data (phone
  messages). A Python block with `if`/`for` inside counts each change as optional.
  Conditions: `budget --before` follows up to 8 flags (variables only ever set to literals,
  never through `SetVariable`/`setattr`/a function or `global`, not `persistent.*`) whose tests separate
  branches with different gains, and drops paths their values rule out; the output lists
  them and splits the range by the top ones (`escorting_jenny=0: 3 to 3`). Conditions on
  other variables, including the counted variable itself (`if tr_aff >= 9` gating more
  gains), still count both ways. Loops: a loop that comes back with the same flag values is
  reported as "can repeat"; every loop gain counts once in the maximum (the range is the
  tighter of the flag and no-flag results, so a hub unrolled per flag value can't count
  the same gain twice). Computed jumps other than the forms above end a path; `recon` prints
  `story:` coverage and the labels it can't reach, and `FLOW_EDGES` in hints.py adds the
  missing links. When a threshold is unreachable, sits in a big loop, or the flags multiply
  paths past the cap (it retries with fewer), `budget` says so; read the code. A flag set
  inside a called label and read after the return is forgotten unless the label is the
  only place it changes. A `show screen` button is only linked where the screen is shown.
  "Unused so far" uses the same graph, so it doesn't depend on file names sorting in story
  order (`script.rpy` often holds the early chapters but sorts after `chapter_N.rpy`); a
  called label's `return` goes back to its callers only within 400 statements of its entry
  (a label that runs on into the story ends the game there instead).
- **Screen-only reads**: stat screens read variables in screen language, which the dump
  does not index. Grep `src/`.
- **Replay-only menus** (`if _in_replay`, or `if <key>` where the gallery passes `key`
  through `Replay(scope={...})`) never show hints; `check` skips them.
- **Gallery detection**: labels quoted in files that call `Replay(` or on lines mentioning
  a gallery (`CharGallery('Title', 'label')`), and persistent flags those files read.
- **Labels without a block** (`label x:` followed by unindented code) run what follows
  them; the dump counts that dialogue. The `label` column is the enclosing block label;
  `show` also prints the nearest label above.
- **Image-button choices** (`show screen A` + `call screen B`, each with a Jump/Return
  button), timed QTE screens and `renpy.display_menu` calls bypass `menu:`; recon lists them.
- **Custom list screens** record choices by list name: list those functions in
  `LIST_SCREENS[...]["unproxy"]`.
- **Typed prompts** (`renpy.input`) can gate content (passwords): add `INPUT_HINTS`. Validation
  loops ("must differ from your name") only need a hint if a player could get stuck.
- **Menu item arguments** (`"text" (enable=cond)`) are passed to the choice screen as
  `item.kwargs`; games use them to grey out items. The dump records them per item.
- **`define persistent.x = 0`** in a game resets that persistent value at every launch
  (a game bug); gallery hints may then overstate what stays unlocked.
- **Re-dumping during parallel analysis**: the dump file is replaced atomically, but `pseudo/`
  is rebuilt; re-dump only when no agent is reading the work dir.
