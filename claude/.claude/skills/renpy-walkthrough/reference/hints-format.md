# hints.py format

`<work dir>/hints.py` is plain Python, read by `rpw.py gen` and `rpw.py check`.

```python
SCOPE = ["*"]                      # fnmatch globs over script paths (relative to game/) that must be fully covered
ANY = "Any choice: dialogue only." # optional override of the default "dialogue only" note
HINT_MAX_LEN = 25                  # optional: narrow choice buttons (recon prints the estimate); default 60
PATCH_DEFINES = {"wt_long_menu_shift": 1.0, "wt_long_menu_from": 1}   # optional: override any `define wt_*` of the template for this game

HINTS = {
    # key: "file:line" of the `menu:` statement, exactly as `rpw.py list` prints it
    "chapter_3.rpy:1309": (None, {                          # (menu note or None, {item index: (kind, text)})
        0: ("good", "Gallery scene · keeps Nora's route"),
        1: ("bad", "No scene · Nora's route ends"),
    }),
    "chapter_4.rpy:349": ("Best combination: Red, Square, Fast.", {2: ("good", "Part of the best combination")}),
    "script.rpy:2900": (None, {0: ("info", "Friendly +1"), 1: ("info", "Witty +1"), 2: ("info", "Aggressive +1")}),
    "chapter_2.rpy:996": "ANY",      # dialogue-only menu: shows the ANY note
    "chapter_3.rpy:120": "SKIP",     # covered on purpose, nothing shown
}

INPUT_HINTS = {
    # "file:line" of the Python statement that calls renpy.input(...): hint text shown above the prompt
    "script.rpy:28525": "Code: Alpha-Seven-Nine (case-sensitive)",
}

SCREEN_NOTES = {
    # "file:line" of a `call screen` (or renpy.call_screen) statement: a note shown at the top while it waits.
    # For choices the patch can't annotate per button: image-button pairs, timers, free-roam maps.
    "chapter_8.rpy:2130": "Spare the guard: extra scenes later in Ch 8.",
}
```

- Kinds: `"good"` green ▲ (a gain), `"bad"` red ▼ (a loss), `"info"` grey ● (neutral:
  equal paths, tone/trait picks, "Torr +1 (not used yet)").
- Item indexes count every entry of the `menu:` block, including a caption line (a
  string without a block) and conditional items. `rpw.py list` shows them.
- `gen` copies the exact raw captions and the menu signature (item 0's caption) from
  the dump; you never type captions.
- `check` skips menus inside replay-only branches and menus with a single
  unconditional option; you don't need entries for them.
- Limits: item hints `HINT_MAX_LEN` (default 60; ~35 for phone/side menus), notes 90.
  No em or en dashes (`check` errors). `[` and `{` are escaped automatically.
  " · " joins two payoffs; the patch keeps the dot from starting a wrapped line.
- Screen notes describe the buttons by their visible text or meaning ("Spare the
  guard"), since the patch can't mark individual buttons. `rpw.py list`'s call-screen
  sites come from `rpw_dump.json` (`callscreens`); recon names the button sets.
- Shared phrasing: define constants at the top (`QUIZ_RIGHT = ("good", "Correct answer")`).

## Story graph links (`FLOW_EDGES`)

When `recon` prints `unreached:` labels (a screen button with a computed target, a jump
inside a Python function), tell `budget` where the story goes:

```python
FLOW_EDGES = {"credits.rpy:5": ["chapter2"], "map.rpy:40": ["beach", "park"]}  # statement -> labels it leads to
```

## Fragments (parallel analysis)

`hints.d/*.py` files are merged into `hints.py` by `gen` and `check`:
- a fragment defines `HINTS`, `INPUT_HINTS`, `SCREEN_NOTES` and/or `FLOW_EDGES` (its own constants are fine;
  `SCOPE`, `ANY`, `LIST_SCREENS`, `PATCH_DEFINES`, `HINT_MAX_LEN` there are ignored with a warning);
- a key defined in two files, or twice in one file, is an error naming both files;
- errors from `check` name the file a key came from;
- `check DIR --only 'a.rpy,b*.rpy'` limits gaps, errors and the summary to those files.

## Custom list screens (`LIST_SCREENS`)

For games whose choices are `call screen <name>("<list name>", ...)` with
`define <list name> = [Choice("text", "label", "condition"), ...]`:

```python
LIST_SCREENS = {"choicescreen": {
    "arg": 0,                   # positional index of the list-name argument (or "kwarg": "choices")
    "text": "text",             # attribute holding the caption
    "unproxy": ["updatechoices"],  # game functions that receive the list name and must see the real one
}}
HINTS = {"@m7choice1": (None, {0: ("good", "Starts Nora's route"), 1: ("bad", "Ends Nora's route")})}
```

The patch re-registers the screen and passes it the same items under a proxy name
(`wt_list__<name>`), hinted ones wrapped so only their caption differs: every other read and
every write (visited flags, `chosen`) reaches the game's own object, and saves hold the
game's objects, never the wrapper or the proxy list. Any game function that records choices by list name
(here `updatechoices(choices, index)`) must be listed in `unproxy`, or the game's
choice history would be keyed by the proxy name. Find them in the screen's button
actions (`rpw.py show DIR @name`, or grep `pseudo/` for the screen).
