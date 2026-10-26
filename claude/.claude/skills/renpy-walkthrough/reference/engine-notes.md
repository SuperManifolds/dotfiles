# Engine notes

Read when recon, verify or preview reports a problem: how the patch hooks into the engine, layout fixes, and how rpw runs games.

## How the patch hooks in (verified on Ren'Py 7.4.10/7.4.11, 8.2.1, 8.3.4, 8.3.7, 8.4.1, 8.5.3)

- Every `menu:` item reaches the `choice` screen as a `MenuEntry` (a tuple subclass) with
  `.caption`, `.action` (`renpy.ui.ChoiceReturn`, with `.sensitive`), `.chosen`, `.args`,
  `.kwargs`. 8.4: `renpy/exports/menuexports.py` (`display_menu`); 8.2:
  `renpy/exports.py:1290-1316`.
- `action.location` is the `Menu` node's name; `renpy.game.script.namemap[location]` returns
  the node with `.filename`, `.linenumber` and `.items[i] = (raw caption, condition, block)`.
  `action.value` is the item's original index.
- Keys use the path relative to `game/` and always `.rpy`: some engines record `.rpyc`
  filenames when scripts load from compiled files.
- Screens register in `renpy.display.screen.screens[(name, variant)]` and
  `screens_by_name[name][variant]`. The patch re-registers the game's screen as
  `wt_orig_<name>` and points `<name>` at a copy of its wrapper that carries the original's
  zorder/modal/tag/layer (and sensitive/roll_forward where the engine has them; 7.4 has no
  `roll_forward`).
- `use` inherits the parent's widget ids (`SLContext(parent)`), so wrapping `input` keeps
  `id "input"` working.
- `renpy.get_filename_line()` is the current statement while `renpy.input` waits.
- Headless lint: `<launcher> <base dir> lint <report>`; `print()` in init code goes to stdout.
- `config.label_overrides` replaces `splashscreen` for `preview`.
- The engine runs Python with `-O`: `assert` statements are stripped. Use `raise` in
  `--setup` checks.

## Layout, preview and runs

- **Repeated captions** ("Yes"/"No" appear dozens of times): key on (file, menu line,
  index) plus stored raw captions and a menu signature, never on caption text.
- **Text filters**: `config.say_menu_text_filter` rewrites names; compare raw captions.
- **Caption decoration**: games wrap the caption (`"{color=#fff}" + i.caption`); the hint
  is appended with explicit size/colour tags that close themselves.
- **Fixed-size buttons** overflow when a line is added: tune mode (`reference/tune-mode.md`).
- **Narrow menus** (phone/side layouts, `xsize 400` buttons): hints wrap; recon estimates
  characters per line; set `HINT_MAX_LEN`.
- **Long menus near the screen edge**: a menu anchored at its top near the bottom (Ripples) has
  no room for extra hint lines; the last items get pushed off screen. Preview a long menu with
  and without hints (`--setup "persistent.wt_enabled = False"`); if hints push items off, set
  `PATCH_DEFINES = {"wt_long_menu_shift": 1.0, "wt_long_menu_from": 1}` to lift every hinted menu by
  the height its hints add (Ripples needed both: its 5-choice party hub overflowed too).
- **Games that reset `config.label_overrides`** after init: preview re-installs its redirect from
  `config.start_callbacks`; `preview-stdout.txt` logs `rpw-preview: showing ...` when it worked.
- **Init priority**: with `init offset = 1`, `init 999` becomes 1000 and is rejected.
- **Python 2 games** (Ren'Py 7): no f-strings in `.rpy` assets; engines print `u'...'` reprs.
- **Translation wrappers**: games with `tl/` ship every line inside `translate` blocks;
  the dumper unwraps them.
- **Parallel engine runs**: rpw serializes engine runs per game folder and runs them with
  `SDL_AUDIODRIVER=dummy` (parallel games deadlocked in CoreAudio before).
- **Preview limits**: runs before `start`, so story variables have their defaults (typed
  names are seeded from the `renpy.input` defaults); pass `--setup` for style switches.
  Conditions are evaluated, so greyed items look as in the game for the given state.
- **Fail-safe patch**: every engine-facing part of the patch is guarded. An error while
  taking over screens undoes the take-over; an error in the self-check or at runtime
  switches the hints off for that launch. Look for `walkthrough: disabled after an error`
  in `log.txt` if hints vanish.
- **Game updates**: `migrate` re-keys hints whose menu captions are unchanged but moved
  (it reads the old captions from the previously generated `walkthrough.rpy`).
- **Background windows**: previews launch `.app` bundles with `open -g` (no focus), move the
  window off screen and exit without saving persistent data, so the window position the game
  remembers is never touched. Quarantined apps run from an App Translocation copy; game errors
  therefore come back through `config.exception_handler` into `DIR/preview-error.txt`.
- **Previewing a `call screen` site** jumps to the statement after the previous interaction
  (dialogue, menu, label or pause), so the setup lines and `show screen` buttons before the
  call run too, and captures once the game is waiting on the call. Story variables still have
  their defaults: pass `--setup` if the screen needs them.
- **Leftovers**: `dump`, `preview` and `verify` remove their files and any `traceback.txt`
  they caused, also when stopped by SIGTERM or a closed terminal. After a hard kill, the next
  `dump`, `verify`, `preview` or `uninstall` removes stray `_rpw_*` scripts and verify's test
  copies of walkthrough.rpy from game/ (and says so). `verify` leaves the previously installed
  patch in place, even when the new one fails.
- **Updates**: use `rpw.py update` (SKILL.md). In game, entries whose menu changed are dropped
  at init and listed in `log.txt` as `walkthrough: ... mismatch`.
