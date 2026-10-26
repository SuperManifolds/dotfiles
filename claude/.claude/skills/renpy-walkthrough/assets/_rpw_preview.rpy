## renpy-walkthrough preview. Copied into game/ by `rpw.py preview` / `verify` and removed right after.
## Inert unless RPW_PREVIEW is set. Instead of the splashscreen it shows a batch of real menus
## ("shots"), saves a screenshot of each (and optionally the on-screen rectangles of every
## clickable button), then exits without saving persistent data.
## Must stay valid under Ren'Py 7 (Python 2) and Ren'Py 8 (Python 3): no f-strings.

init 999 python:
    import os as _rpw_os
    import json as _rpw_json

    _rpw_preview_spec = _rpw_json.loads(_rpw_os.environ["RPW_PREVIEW"]) if _rpw_os.environ.get("RPW_PREVIEW") else None

    def _rpw_redirect_splash():
        config.label_overrides["splashscreen"] = "_rpw_preview"

    def _rpw_error_text(args):
        """Traceback text from either handler signature: (TracebackException) in 8.4+, (short, full, file) before."""
        if len(args) != 1:
            return u"%s" % (args[1] if len(args) > 1 else args,)
        te = args[0]
        try:
            import io
            buf = io.StringIO()
            te.format(renpy.error.NonColoredExceptionPrintContext(buf, filter_private=False))
            return buf.getvalue()
        except Exception:
            return u"%s" % (te,)

    def _rpw_on_error(*args):
        """Write the error where rpw can read it (the game folder may be read-only) and quit at once."""
        try:
            import io
            with io.open(_rpw_preview_spec["err"], "w", encoding="utf-8") as f:
                f.write(_rpw_error_text(args))
        finally:
            _rpw_os._exit(3)

    if _rpw_preview_spec:
        if _rpw_os.environ.get("RPW_PIDFILE"):
            # rpw kills exactly this process on a timeout, never another copy of the game.
            with open(_rpw_os.environ["RPW_PIDFILE"], "w") as _rpw_f:
                _rpw_f.write("%d" % _rpw_os.getpid())
        if _rpw_preview_spec.get("err"):
            config.exception_handler = _rpw_on_error
        _rpw_redirect_splash()
        # Some games clear config.label_overrides after init; start callbacks run right before the splashscreen.
        config.start_callbacks.append(_rpw_redirect_splash)
        print("rpw-preview: splashscreen redirected")

    def _rpw_menu_items(shot):
        for node in renpy.game.script.namemap.values():
            if isinstance(node, renpy.ast.Menu) and wt_key(node.filename, node.linenumber) == (shot["file"], shot["line"]):
                items = []
                for i, (label, cond, block) in enumerate(node.items):
                    if block is None:
                        items.append((label, None))
                        continue
                    try:
                        ok = bool(renpy.python.py_eval(cond))
                    except Exception:
                        ok = True
                    if ok or config.menu_include_disabled:
                        items.append((label, renpy.ui.ChoiceReturn(label, i, node.name, sensitive=ok)))
                return items
        raise Exception("rpw preview: no menu at %s:%d" % (shot["file"], shot["line"]))

    def _rpw_capture(shot):
        """Screenshot, plus the rectangles of every clickable element when the shot asks for a probe."""
        if shot.get("probe"):
            rects = [[f.x, f.y, f.w, f.h] for f in renpy.display.focus.focus_list if f.x is not None]
            with open(shot["probe"], "w") as f:
                f.write(_rpw_json.dumps({"rects": rects, "width": config.screen_width, "height": config.screen_height}))
        renpy.screenshot(shot["out"])

    def _rpw_finish():
        print("rpw-preview: done")
        _rpw_os._exit(0)

    def _rpw_capture_at_site(shot):
        """For a `call screen` shot: capture once the game is waiting on that statement (the statements run
        before it may still be playing transitions)."""
        if wt_key(*renpy.get_filename_line()) != (shot["goto"][0], shot["goto"][1]):
            return
        if not shot.get("arrived"):
            shot["arrived"] = True  # capture on the next tick, once the screen has settled
            return
        _rpw_capture(shot)
        _rpw_finish()

    def _rpw_site(shot):
        """Where to jump to run a `call screen` statement in place: a few statements before it, right after
        the previous interaction, so the setup it relies on (`$ timer = ...`, `show screen` buttons) runs too."""
        target = None
        prev = {}
        for node in renpy.game.script.namemap.values():
            nxt = getattr(node, "next", None)
            if nxt is not None:
                prev[id(nxt)] = node
            if wt_key(node.filename, node.linenumber) == (shot["goto"][0], shot["goto"][1]) and \
                    isinstance(node, (renpy.ast.UserStatement, renpy.ast.Python)):
                target = node
        if target is None:
            raise Exception("rpw preview: no statement at %s:%d" % tuple(shot["goto"]))
        start = target
        for _i in range(30):
            before = prev.get(id(start))
            if before is None or before.filename != target.filename or isinstance(before, (renpy.ast.Say, renpy.ast.Menu, renpy.ast.Label)):
                break
            if isinstance(before, renpy.ast.UserStatement) and before.line.split()[:1] in (["pause"], ["call"]):
                break
            start = before
        return start.name

    def _rpw_move_window_away():
        """Keep the window out of sight. The position is not saved: the preview exits without saving persistent data."""
        try:
            import pygame_sdl2
            pygame_sdl2.display.get_window().set_position(-30000, -30000)
        except Exception:
            pass

screen _rpw_preview_timer(shot, delay):
    # Above every game screen: a modal choice screen would otherwise swallow the timer event.
    zorder 10000
    if shot.get("goto"):
        timer delay repeat True action Function(_rpw_capture_at_site, shot)
    else:
        timer delay action [Function(_rpw_capture, shot), Return(True)]

label _rpw_preview:
    python:
        if _rpw_preview_spec.get("hide_window", True):
            _rpw_move_window_away()
        # The preview runs inside the splashscreen, which hides overlay screens (screen notes use one).
        store.suppress_overlay = False
        for _rpw_shot in _rpw_preview_spec["shots"]:
            print("rpw-preview: showing %s" % (_rpw_shot.get("label") or "%s:%s" % (_rpw_shot.get("file"), _rpw_shot.get("line")),))
            persistent.wt_enabled = True
            if _rpw_shot.get("setup"):
                exec(_rpw_shot["setup"], store.__dict__)
            renpy.show_screen("_rpw_preview_timer", _rpw_shot, _rpw_preview_spec.get("delay", 2.0))
            if _rpw_shot.get("goto"):
                # Run the game's own `call screen` statement in place; the timer captures it and exits.
                renpy.jump(_rpw_site(_rpw_shot))
            if _rpw_shot.get("call"):
                eval(_rpw_shot["call"], store.__dict__)
            else:
                renpy.display_menu(_rpw_menu_items(_rpw_shot))
            renpy.hide_screen("_rpw_preview_timer")
        print("rpw-preview: done")
        _rpw_os._exit(0)
