# Tune mode (fixed-size choice buttons)

Use when `recon` prints "tune mode suggested": the game's `screen choice` sets a fixed
`xysize`/`ysize`/`ymaximum` on its buttons, so a second caption line overflows. Check
first with `rpw.py preview` on a menu with a long caption: if the generic wrapper fits,
stay with it.

Tune mode replaces the game's choice screen with a copy that has room for the hint:

1. Copy the game's `screen choice(items)` from `DIR/src/` (or `pseudo/`) into
   `DIR/screen_choice.rpy`. `gen` appends that file to the patch, skips the wrapper, and
   the self-check reports `wrapped {'choice': 'tuned'}`.
2. In the copy, for each item:
   ```renpy
   $ wt_hint = wt_item_hint(i) if wt_active() else None
   if wt_hint is None:
       # the game's original button, unchanged
   else:
       button:
           vbox:
               align (0.5, 0.5)
               spacing 4
               text i.caption ...game's text properties... text_align 0.5
               text wt_hint_line(wt_hint[0], wt_hint[1]) substitute False size <hint size> xalign 0.5
           action i.action
           background Frame("<the game's button image>", 16, 16)
           xsize <the game's width>
           yminimum <the game's height>
           ypadding 12
   ```
3. Add the note line and the status label (copy them from `screen wt_overlay` in the
   template, or `use wt_overlay(wt_menu_note(items))` inside the screen).
4. Name the copy `choice`; `init offset = 1` in the patch makes it win.
5. Use only the patch's helpers in the copy (`wt_item_hint`, `wt_hint_line`, `wt_menu_note`,
   `wt_active`): they are guarded, so an error in them switches the hints off instead of
   crashing the game. Don't call engine internals directly from the tuned screen.
6. `rpw.py gen`, `verify --negative`, `preview` as usual.

Worked example: `~/renpy-walkthroughs/companion-of-darkness/screen_choice.rpy`
(Companion of Darkness 1 and 2 share this 885×84 button). A `Frame` around an SVG
button can show thin stubs at the corners; try larger borders if it does.
