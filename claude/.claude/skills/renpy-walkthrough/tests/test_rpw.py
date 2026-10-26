"""Unit tests for rpw.py that need no game: they run on a fixture work dir (tests/fixtures/mini)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
RPW = os.path.join(SKILL, "rpw.py")
FIXTURE = os.path.join(HERE, "fixtures", "mini")
sys.path.insert(0, SKILL)
import rpw  # noqa: E402


class WorkDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rpw-test-")
        self.work = os.path.join(self.tmp, "mini")
        shutil.copytree(FIXTURE, self.work)
        dump = os.path.join(self.work, "rpw_dump.json")
        data = json.loads(rpw.read_text(dump))
        data["dumper"] = rpw.dumper_hash()
        rpw.write_text(dump, json.dumps(data))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_rpw(self, *args):
        p = subprocess.run([sys.executable, "-I", RPW] + list(args), capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def write(self, rel, text):
        with open(os.path.join(self.work, rel), "w") as f:
            f.write(text)


class CheckTest(WorkDirTest):
    def test_fixture_passes_and_auto_skips(self):
        code, out, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 0, out + err)
        self.assertIn("0 errors, 0 gaps", out)
        self.assertIn("auto-skipped: 1 replay-only + 1 single-option", out)
        self.assertNotIn("Traceback", err)

    def test_missing_fragment_is_a_gap(self):
        os.remove(os.path.join(self.work, "hints.d", "part.py"))
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("gap: ch2.rpy:5", out)

    def test_only_scopes_gaps_and_counts(self):
        os.remove(os.path.join(self.work, "hints.d", "part.py"))
        code, out, _ = self.run_rpw("check", self.work, "--only", "script.rpy")
        self.assertEqual(code, 0, out)
        self.assertIn("[--only script.rpy]", out)

    def test_bad_value_names_its_file(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": "SKIPP"}\n')
        code, out, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("hints.d/part.py", out)
        self.assertNotIn("Traceback", err)

    def test_dash_is_an_error(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": (None, {1: ("good", "Scene — later")})}\n')
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("em or en dash", out)

    def test_malformed_hints_are_errors_not_crashes(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": (3, {-1: ("good", "x"), "1": ("good", "y"), '
                                      '2: ("good", ("a", "b"))})}\n')
        code, out, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("the note must be a string", out)
        self.assertEqual(out.count("the item index must be a whole number"), 2)
        self.assertIn("hint text must be a string", out)

    def test_only_reads_the_file_name_of_each_error(self):
        wanted = lambda fn: fn == "intro.rpy"
        key_file = lambda key: "intro.rpy" if key == ("@list", "m1") else ""
        for error in ("intro.rpy:5[1] (hints.d/a.py): kind 'great' is not one of ('good', 'bad', 'info')",
                      "input intro.rpy:3: contains an em or en dash", "screen note intro.rpy:9: contains an em or en dash",
                      "'intro.rpy: 5' (hints.py): key must be 'file.rpy:LINE' with no spaces", "@m1 (hints.py): bad"):
            self.assertTrue(rpw.error_in_scope(error, wanted, key_file), error)
        self.assertFalse(rpw.error_in_scope("ch2.rpy:5 (hints.py): no menu statement at that line", wanted, key_file))

    def test_dash_in_input_hint_and_fragment_screen_note(self):
        self.write("hints.d/notes.py", 'INPUT_HINTS = {"script.rpy:3": "Name \\u2014 any"}\n'
                                       'SCREEN_NOTES = {"script.rpy:50": "Pick left \\u2013 always"}\n')
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("input script.rpy:3: contains an em or en dash", out)
        self.assertIn("screen note script.rpy:50: contains an em or en dash", out)

    def test_unknown_kind_is_an_error(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": (None, {1: ("great", "Scene")})}\n')
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("kind 'great'", out)

    def test_duplicate_key_across_files(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": "ANY", "script.rpy:10": "ANY"}\n')
        code, _, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("already defined in hints.py", err)

    def test_duplicate_key_in_one_file(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": "ANY", "ch2.rpy:5": "SKIP"}\n')
        code, _, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("defined twice", err)

    def test_syntax_error_names_fragment(self):
        self.write("hints.d/part.py", "HINTS = {\n")
        code, _, err = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("part.py", err)
        self.assertNotIn("Traceback", err)

    def test_hint_max_len_override(self):
        self.write("hints.d/part.py", 'HINTS = {"ch2.rpy:5": (None, {1: ("good", "x" * 30)})}\n')
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write("HINT_MAX_LEN = 20\n")
        _, out, _ = self.run_rpw("check", self.work)
        self.assertIn("hint is 30 chars (max 20)", out)


class GenTest(WorkDirTest):
    def test_gen_fills_captions_lists_and_wrappers(self):
        code, out, err = self.run_rpw("gen", self.work)
        self.assertEqual(code, 0, out + err)
        text = rpw.read_text(os.path.join(self.work, "walkthrough.rpy"))
        self.assertIn("('script.rpy', 10): {\"sig\": 'Help her'", text)
        self.assertIn("1: ('Walk away', 'bad', 'Trust -1'),", text)
        self.assertIn("('@list', 'm1'): {\"sig\": 'Go left'", text)
        self.assertIn("screen wt_list_picker(*args, **kwargs):", text)
        self.assertIn("define wt_list_screens = {'picker'", text)
        self.assertIn("define wt_tuned = False", text)
        self.assertNotIn("@HINTS@", text)
        self.assertNotIn("@LISTS@", text)

    def test_tune_file_is_appended(self):
        self.write("screen_choice.rpy", "screen choice(items):\n    pass\n")
        self.run_rpw("gen", self.work)
        text = rpw.read_text(os.path.join(self.work, "walkthrough.rpy"))
        self.assertIn("define wt_tuned = True", text)
        self.assertTrue(text.rstrip().endswith("pass"))


    def test_patch_defines_override_template(self):
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('PATCH_DEFINES = {"wt_long_menu_shift": 1.0}\n')
        self.run_rpw("gen", self.work)
        text = rpw.read_text(os.path.join(self.work, "walkthrough.rpy"))
        self.assertIn("define wt_long_menu_shift = 1.0", text)

    def test_patch_defines_unknown_name(self):
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('PATCH_DEFINES = {"wt_no_such_knob": 1}\n')
        code, _, err = self.run_rpw("gen", self.work)
        self.assertEqual(code, 1)
        self.assertIn("wt_no_such_knob", err)


class ScreenNoteTest(WorkDirTest):
    def test_screen_note_is_generated_and_checked(self):
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('SCREEN_NOTES = {"script.rpy:50": "Pick left: extra scene."}\n')
        code, out, err = self.run_rpw("gen", self.work)
        self.assertEqual(code, 0, out + err)
        text = rpw.read_text(os.path.join(self.work, "walkthrough.rpy"))
        self.assertIn("('script.rpy', 50): ('call screen picker(\"m1\", \"left\")', 'Pick left: extra scene.'),", text)
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 0, out)
        self.assertIn("1 screen notes", out)

    def test_screen_note_on_a_non_screen_line(self):
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('SCREEN_NOTES = {"script.rpy:51": "Nothing here."}\n')
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("no `call screen`", out)


class SpotcheckTest(WorkDirTest):
    def test_brief_and_compare(self):
        code, out, err = self.run_rpw("spotcheck", self.work, "--sample", "3", "--seed", "1")
        self.assertEqual(code, 0, out + err)
        brief = rpw.read_text(os.path.join(self.work, "spotcheck", "brief.md"))
        self.assertIn("`script.rpy:10`", brief)
        self.assertNotIn("Trust +2", brief)              # the brief never leaks our hints
        self.write("spotcheck/blind.py", 'HINTS = {"script.rpy:10": (None, {0: ("bad", "x"), 1: ("bad", "y")}), '
                                         '"@m1": (None, {1: ("good", "z")})}\n')
        code, out, _ = self.run_rpw("spotcheck", self.work, "--compare")
        self.assertEqual(code, 0, out)
        self.assertIn("conflict  script.rpy:10[0]", out)
        self.assertIn("missed    @m1[1]", out)
        self.assertIn("1 agree", out)


class MigrateTest(WorkDirTest):
    def shift_menus(self, moves, rename=None):
        """Simulate a game update: move menus to new lines (and optionally change a caption)."""
        dump = os.path.join(self.work, "rpw_dump.json")
        data = json.loads(rpw.read_text(dump))
        for m in data["menus"]:
            key = "%s:%d" % (m["file"], m["line"])
            if key in moves:
                m["line"] = moves[key]
            if rename and key == rename[0]:
                m["items"][rename[1]]["caption"] = rename[2]
        rpw.write_text(dump, json.dumps(data))

    def test_moves_keys_in_hints_and_fragments(self):
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        self.shift_menus({"script.rpy:10": 12, "ch2.rpy:5": 9})
        code, out, err = self.run_rpw("migrate", self.work)
        self.assertEqual(code, 0, out + err)
        self.assertIn("move  script.rpy:10 -> script.rpy:12", out)
        self.assertIn("move  ch2.rpy:5 -> ch2.rpy:9", out)
        self.assertIn('"script.rpy:10"', rpw.read_text(os.path.join(self.work, "hints.py")))  # dry run
        self.assertEqual(self.run_rpw("migrate", self.work, "--write")[0], 0)
        self.assertIn('"script.rpy:12"', rpw.read_text(os.path.join(self.work, "hints.py")))
        self.assertIn('"ch2.rpy:9"', rpw.read_text(os.path.join(self.work, "hints.d", "part.py")))
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 0, out)

    def test_unused_hint_flagged_when_variable_gains_a_read(self):
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('HINTS["script.rpy:10"] = (None, {0: ("info", "Trust +2 (not used yet)")})\n')
        dump = os.path.join(self.work, "rpw_dump.json")
        prev = os.path.join(self.work, "rpw_dump.prev.json")
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        data = json.loads(rpw.read_text(dump))
        rpw.write_text(prev, json.dumps(data))
        _, out, _ = self.run_rpw("migrate", self.work)
        self.assertNotIn("recheck", out)                 # trust was already read before the "update"
        old = dict(data, reads=[r for r in data["reads"] if r["kind"] == "python"])
        rpw.write_text(prev, json.dumps(old))
        code, out, _ = self.run_rpw("migrate", self.work)
        self.assertIn("recheck script.rpy:10[0]", out)   # the read in ch2.rpy is new with the update
        self.assertEqual(code, 1)

    def test_changed_caption_needs_a_human(self):
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        self.shift_menus({"script.rpy:10": 12}, rename=("script.rpy:10", 0, "Help her (new text)"))
        code, out, _ = self.run_rpw("migrate", self.work)
        self.assertIn("lost  script.rpy:10", out)
        self.assertIn("menu text changed or removed", out)
        self.assertEqual(code, 1)

    def test_two_keys_moving_onto_one_menu_need_a_human(self):
        dump = os.path.join(self.work, "rpw_dump.json")
        data = json.loads(rpw.read_text(dump))
        first = next(m for m in data["menus"] if m["line"] == 10)
        twin = json.loads(json.dumps(first))
        twin["line"] = 15
        data["menus"].append(twin)  # a copy-pasted menu
        rpw.write_text(dump, json.dumps(data))
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('HINTS["script.rpy:15"] = (None, {0: ("good", "Trust +2")})\n')
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        data["menus"] = [m for m in data["menus"] if m["line"] not in (10, 15)] + [dict(first, line=40)]
        rpw.write_text(dump, json.dumps(data))  # the update removed one copy and moved the other
        code, out, _ = self.run_rpw("migrate", self.work, "--write")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("2 keys would move to the same menu"), 2)
        self.assertIn('"script.rpy:10"', rpw.read_text(os.path.join(self.work, "hints.py")))

    def test_write_keeps_a_backup(self):
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        self.shift_menus({"script.rpy:10": 12})
        self.assertEqual(self.run_rpw("migrate", self.work, "--write")[0], 0)
        self.assertIn('"script.rpy:10"', rpw.read_text(os.path.join(self.work, "hints.py.bak")))

    def test_check_catches_another_menu_on_a_hinted_line(self):
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)
        self.shift_menus({}, rename=("script.rpy:10", 0, "Betray her"))
        code, out, _ = self.run_rpw("check", self.work)
        self.assertEqual(code, 1)
        self.assertIn("script.rpy:10: this menu changed since walkthrough.rpy was generated", out)


class HelperTest(WorkDirTest):
    def test_budget_lists_start_and_changes(self):
        code, out, _ = self.run_rpw("budget", self.work, "trust")
        self.assertEqual(code, 0)
        lines = out.strip().split("\n")
        self.assertIn("default", lines[0])
        self.assertIn("(choice script.rpy:10[0])", out)
        self.assertIn("1 increments, 1 decrements, 1 threshold reads", out)

    def test_budget_before_follows_story_paths(self):
        # start -> menu script.rpy:10 -> trust += 2 (L11) or trust -= 1 (L13) -> ch2.rpy:40 `if trust >= 2`
        nodes = [[0, 1, "n", [1], None], [0, 10, "n", [2, 3], None], [0, 11, "p", [4], None],
                 [0, 13, "p", [4], None], [1, 40, "n", [], None]]
        self.write(rpw.CFG, json.dumps({"files": ["script.rpy", "ch2.rpy"], "labels": {"start": 0}, "nodes": nodes}))
        code, out, _ = self.run_rpw("budget", self.work, "trust", "--before", "ch2.rpy:40")
        self.assertEqual(code, 0)
        self.assertIn("along story paths from `start`: 0 to 3 (start 1)", out)
        code, out, _ = self.run_rpw("budget", self.work, "trust", "--before", "ch2.rpy:40", "--via", "script.rpy:13")
        self.assertIn("through script.rpy:13: 0 to 0 (start 1)", out)

    def test_check_warns_when_a_not_used_yet_stat_is_read_later(self):
        nodes = [[0, 1, "n", [1], None], [0, 10, "n", [2, 3], None], [0, 11, "p", [4], None],
                 [0, 13, "p", [4], None], [1, 40, "n", [], None]]
        self.write(rpw.CFG, json.dumps({"files": ["script.rpy", "ch2.rpy"], "labels": {"start": 0}, "nodes": nodes}))
        with open(os.path.join(self.work, "hints.py"), "a") as f:
            f.write('HINTS["script.rpy:10"] = (None, {0: ("info", "Trust +2 (not used yet)")})\n')
        _, out, _ = self.run_rpw("check", self.work)
        self.assertIn("script.rpy:10[0]: the hint says 'Trust +2 (not used yet)', but a story read of trust", out)

    def test_other_menu_screen(self):
        self.assertEqual(rpw.other_menu_screen({"arguments": '(screen="phone_choice")'}), "screen 'phone_choice'")
        self.assertEqual(rpw.other_menu_screen({"arguments": "(nvl=True)"}), "the NVL screen")
        self.assertIsNone(rpw.other_menu_screen({"arguments": '(screen="choice")'}))
        self.assertIsNone(rpw.other_menu_screen({"arguments": ""}))

    def test_input_defaults(self):
        self.assertIn("mcname = 'Liam'", rpw.input_defaults(self.work))

    def test_list_items_parse_conditions(self):
        items = rpw.parse_list_items('[Choice("A", "a"), Choice("B", "b", "x > 1")]')
        self.assertEqual([(i["caption"], i["label"], i["condition"]) for i in items],
                         [("A", "a", "True"), ("B", "b", "x > 1")])
        self.assertIsNone(rpw.parse_list_items("some_function()"))

    def test_width_estimate(self):
        d = rpw.load_dump(self.work)
        self.assertEqual(rpw.hint_chars_estimate(self.work, d, None), 27)

    def test_outside_replay(self):
        self.assertIs(rpw.outside_replay("_in_replay and persistent.scene17"), False)
        self.assertIs(rpw.outside_replay("not _in_replay"), True)
        self.assertIs(rpw.outside_replay("_in_replay == None"), True)
        self.assertIsNone(rpw.outside_replay("seen or (_in_replay and persistent.seen)"))

    def test_wrapped_items(self):
        off = [[0, 100, 500, 40], [0, 160, 500, 40], [0, 220, 500, 40], [800, 1000, 60, 30]]
        on = [[0, 100, 500, 70], [0, 190, 500, 100], [0, 310, 500, 40], [800, 1000, 60, 30]]
        self.assertEqual(rpw.wrapped_items(on, off, None), 1)   # +30 is one line, +60 wrapped
        self.assertEqual(rpw.wrapped_items(off, off, None), 0)

    def test_natural_order(self):
        self.assertEqual(sorted(["chapter_10.rpy", "chapter_5.rpy"], key=rpw.natural_key), ["chapter_5.rpy", "chapter_10.rpy"])

    def test_render_pick_prefers_item_hints(self):
        table = {("a.rpy", 1): {"sig": "x", "note": "n", "items": {}},
                 ("b.rpy", 2): {"sig": "y", "note": None, "items": {0: ("Short", "good", "Hint")}}}
        self.assertEqual(rpw.render_pick(table), "b.rpy:2")

    def test_list_rows_include_lists(self):
        code, out, _ = self.run_rpw("list", self.work)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("#key"))
        self.assertIn("@m1\tpicker\t1\tchoice\ttrust > 0\tGo right", out)


class FakeProc(object):
    """Stands in for the `open -W` (or launcher) process behind a GameProcess."""

    def __init__(self, exited=False, hang=False):
        self.exited, self.hang, self.killed, self.waits = exited, hang, False, 0

    def poll(self):
        return 0 if self.exited else None

    def wait(self, timeout=None):
        self.waits += 1
        if self.hang and self.waits == 1:
            raise subprocess.TimeoutExpired("open", timeout)
        return 0

    def kill(self):
        self.killed = True


class CommandTest(WorkDirTest):
    """Commands that touch the game folder or launch the engine, with the engine replaced by fakes."""

    def setUp(self):
        WorkDirTest.setUp(self)
        self.game_dir = os.path.join(self.tmp, "game")
        os.makedirs(self.game_dir)
        meta = json.loads(rpw.read_text(os.path.join(self.work, "game.json")))
        meta["game_dir"] = self.game_dir
        rpw.write_text(os.path.join(self.work, "game.json"), json.dumps(meta))
        self.assertEqual(self.run_rpw("gen", self.work)[0], 0)

    def args(self, **kw):
        import argparse
        return argparse.Namespace(work_dir=self.work, **kw)

    def test_install_and_uninstall_clean_up_everything(self):
        self.assertEqual(self.run_rpw("install", self.work)[0], 0)
        self.assertTrue(os.path.exists(os.path.join(self.game_dir, rpw.PATCH)))
        for name in (rpw.PATCH + "c", rpw.PREVIEW, rpw.DUMPER + "c"):
            rpw.write_text(os.path.join(self.game_dir, name), "")
        self.assertEqual(self.run_rpw("uninstall", self.work)[0], 0)
        self.assertEqual(os.listdir(self.game_dir), [])

    def test_failing_verify_restores_the_installed_patch(self):
        installed = os.path.join(self.game_dir, rpw.PATCH)
        rpw.write_text(installed, "# the patch the user had installed\n")
        rpw.write_text(os.path.join(self.work, "lint-baseline.txt"), "")

        def fake_lint(work, game, patch_text, label):
            rpw.write_text(installed, patch_text)  # like the real one: the tested patch sits in game/
            return 0, "no self-check here", [], [], ""
        saved = rpw.lint_with
        rpw.lint_with = fake_lint
        try:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as stop:
                rpw.cmd_verify(self.args(negative=False, keep=False, no_render=True))
        finally:
            rpw.lint_with = saved
        self.assertEqual(stop.exception.code, 1)
        self.assertEqual(rpw.read_text(installed), "# the patch the user had installed\n")

    def test_update_stops_when_migrate_or_check_need_a_human(self):
        for codes, expect_exit, expect_steps in (({"migrate": 1}, 1, ["dump", "migrate"]),
                                                 ({"check": 1}, 1, ["dump", "migrate", "check"]),
                                                 ({}, None, ["dump", "migrate", "check", "gen", "verify", "install"])):
            steps = []

            def fake_step(name, argv, allow_fail=False):
                steps.append(name)
                return codes.get(name, 0)
            saved = rpw.run_step
            rpw.run_step = fake_step
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    if expect_exit is None:
                        rpw.cmd_update(self.args())
                    else:
                        with self.assertRaises(SystemExit) as stop:
                            rpw.cmd_update(self.args())
                        self.assertEqual(stop.exception.code, expect_exit)
            finally:
                rpw.run_step = saved
            self.assertEqual(steps, expect_steps)

    def test_failed_dump_keeps_the_old_dump(self):
        import argparse
        old = rpw.read_text(os.path.join(self.work, "rpw_dump.json"))
        saved = rpw.dump_run

        def failing_run(*a):
            rpw.die("engine crashed")
        rpw.dump_run = failing_run
        try:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                rpw.cmd_dump(argparse.Namespace(target=self.work, work=self.work, extract_to=None))
        finally:
            rpw.dump_run = saved
        self.assertEqual(rpw.read_text(os.path.join(self.work, "rpw_dump.json")), old)
        self.assertFalse([n for n in os.listdir(self.work) if n.endswith(".new")])

    def test_readme_force_keeps_the_notes(self):
        self.assertEqual(self.run_rpw("readme", self.work, "--notes", "Nora's route needs 4 trust.")[0], 0)
        self.assertEqual(self.run_rpw("readme", self.work)[0], 1)  # exists: needs --force
        self.assertEqual(self.run_rpw("readme", self.work, "--force")[0], 0)
        self.assertIn("Nora's route needs 4 trust.", rpw.read_text(os.path.join(self.work, "README.md")))

    def test_spotcheck_edges(self):
        code, _, err = self.run_rpw("spotcheck", self.work, "--sample", "0")
        self.assertEqual(code, 1)
        self.assertIn("--sample must be at least 1", err)
        code, _, err = self.run_rpw("spotcheck", self.work, "--compare")
        self.assertIn("sample.json missing", err)
        self.assertEqual(self.run_rpw("spotcheck", self.work, "--sample", "2", "--seed", "1")[0], 0)
        self.write("spotcheck/blind.py", "HINTS = {}\n")
        code, out, _ = self.run_rpw("spotcheck", self.work, "--compare")
        self.assertIn("0 overclaim, 0 minor, 2 unanswered", out)


class ProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rpw-proc-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def mac_game(self, proc):
        game = rpw.GameProcess.__new__(rpw.GameProcess)
        game.exe, game.mac_app, game.proc = "/Apps/Mini.app/Contents/MacOS/Mini", True, proc
        game.pid_path = os.path.join(self.tmp, "out.pid")
        return game

    def test_kill_uses_the_pid_file_and_never_touches_a_finished_game(self):
        from unittest import mock
        game = self.mac_game(FakeProc(exited=True))
        rpw.write_text(game.pid_path, "4242")
        with mock.patch.object(rpw.os, "kill") as kill, mock.patch.object(rpw.subprocess, "run") as run:
            game.kill()
            kill.assert_not_called()  # the game quit: any process found now is someone else's
            run.assert_not_called()
            game.proc = FakeProc()
            game.kill()
            kill.assert_called_once_with(4242, rpw.signal.SIGKILL)
            run.assert_not_called()   # no guessing with pgrep when the pid is known

    def test_wait_gives_up_instead_of_hanging(self):
        game = self.mac_game(FakeProc(hang=True))
        game.wait(timeout=0.01)
        self.assertTrue(game.proc.killed)

    def test_wait_for_preview_kills_on_timeout(self):
        from unittest import mock
        game = self.mac_game(FakeProc())
        with mock.patch.object(rpw, "PREVIEW_TIMEOUT", 0), mock.patch.object(game, "kill") as kill:
            note = rpw.wait_for_preview(game, (), rpw.time.time() - 1)
        kill.assert_called_once()
        self.assertIn("timed out", note)


class SafetyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rpw-safety-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_clean_leftovers_keeps_real_patches_only(self):
        real = rpw.read_text(os.path.join(SKILL, "assets", "walkthrough.rpy.tmpl"))
        crash = real.replace("# @RPW-CRASH-TEST-INIT@", rpw.CRASH + "  " + rpw.CRASH_COPY)
        for text, kept in ((real, True), (crash, False), ('"RPW-NEGATIVE Help her"', False)):
            rpw.write_text(os.path.join(self.tmp, rpw.PATCH), text)
            for name in (rpw.PREVIEW, rpw.DUMPER + "c"):
                rpw.write_text(os.path.join(self.tmp, name), "")
            with contextlib.redirect_stdout(io.StringIO()):
                rpw.clean_leftovers({"game_dir": self.tmp})
            self.assertEqual(os.listdir(self.tmp), [rpw.PATCH] if kept else [])

    def test_zip_ignores_macosx_and_gets_its_own_folder_when_it_has_several_tops(self):
        import zipfile
        path = os.path.join(self.tmp, "Game-1.0-mac.zip")
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("Game.app/Contents/x.txt", "x")
            zf.writestr("__MACOSX/Game.app/._x.txt", "junk")
            zf.writestr(".DS_Store", "junk")
        self.assertEqual(rpw.zip_tops(path), ["Game.app"])
        with contextlib.redirect_stdout(io.StringIO()):
            rpw.extract_zip(path, self.tmp)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "__MACOSX")))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "Game.app", "Contents", "x.txt")))

    def test_rpa_3_2_key_and_no_code_in_the_index(self):
        import pickle
        import zlib

        def archive(name, index_obj, header):
            path = os.path.join(self.tmp, name)
            data = zlib.compress(pickle.dumps(index_obj, protocol=2))
            with open(path, "wb") as f:
                head = (header % 0).encode("latin-1")
                f.write((header % len(head)).encode("latin-1"))
                f.write(data)
            return path

        key = 0x12345678 ^ 0x0000FFFF
        good = archive("a.rpa", {"script.rpyc": [(100 ^ key, 50 ^ key)]}, "RPA-3.2 %016x 00000000 12345678 0000ffff\n")
        self.assertEqual(rpw.read_rpa_index(good), {"script.rpyc": [(100, 50, b"")]})
        evil = archive("b.rpa", {"x": [(1, 2)], "y": Choice("boom")}, "RPA-3.0 %016x 00000000\n")
        with self.assertRaises(ValueError):
            rpw.read_rpa_index(evil)

    def test_call_arguments_and_slugs(self):
        self.assertEqual(rpw.call_arguments('call screen pick("m1", "left") with dissolve'), '"m1", "left"')
        self.assertEqual(rpw.call_arguments('call screen pick(f("a)"), 2)'), 'f("a)"), 2')
        self.assertEqual(rpw.slugify("Ripples-0.9.22-mac.zip"), "ripples")
        self.assertEqual(rpw.slugify("MyGame-1.2-pc-windows.zip"), "my-game")
        self.assertTrue(rpw.slugify("\u30b2\u30fc\u30e0.app").startswith("game-"))


class Choice(object):
    """A game's list-screen item (module level, so pickle can find it)."""

    def __init__(self, text):
        self.text, self.chosen = text, False


class TemplateTest(unittest.TestCase):
    def test_list_item_wrapper_forwards_and_pickles_as_the_game_object(self):
        import copy as copy_module
        import pickle
        src = rpw.read_text(os.path.join(SKILL, "assets", "walkthrough.rpy.tmpl"))
        block = src[src.index("    try:\n        import builtins as _wt_builtins"):src.index("    wt_list_proxies = {}")]
        ns = {}
        exec("\n".join(line[4:] for line in block.split("\n")), ns)

        orig = Choice("Yes")
        w = ns["WtHinted"](orig, "text", "Yes (hint)")
        self.assertEqual((w.text, orig.text), ("Yes (hint)", "Yes"))
        w.chosen = True
        self.assertTrue(orig.chosen)
        self.assertIsInstance(w, Choice)
        self.assertEqual(w, orig)
        back = pickle.loads(pickle.dumps([w, orig]))
        self.assertIs(type(back[0]), Choice)
        self.assertIs(back[0], back[1])
        self.assertIs(type(copy_module.copy(w)), Choice)


def graph(spec, labels):
    """A story graph in rpw_cfg.json form from {node: (kind, successors, call target)}; every node on line = index."""
    nodes = [[0, i, spec[i][0], list(spec[i][1]), spec[i][2] if len(spec[i]) > 2 else None] for i in range(len(spec))]
    return {"files": ["s.rpy"], "labels": labels, "nodes": nodes}


def add(n):
    return (float(n), rpw.NEG)


class StoryFlowTest(unittest.TestCase):
    def reach(self, cfg, effects, target, side=None, flags=None):
        lo_hi = []
        for sign in (1, -1):
            eff = dict((u, (sign * f[0], f[1]) if f[1] == rpw.NEG else (rpw.NEG, sign * f[1])) for u, f in effects.items())
            flow = rpw.StoryFlow(cfg, eff, {}, side, flags)
            state_in = flow.solve([flow.state(cfg["labels"]["start"])], True)[0]
            f = rpw.UNREACHED
            for g in rpw.at_nodes(state_in, {target}).values():
                f = rpw.join(f, g)
            lo_hi.append(sign * rpw.apply_fn(f, 0.0) + 0.0)
        return lo_hi[1], lo_hi[0]

    def test_exclusive_branches_do_not_add_up(self):
        # 0 start -> 1 menu -> 2 (+2) -> 3 (+3) -> 5 target;  menu -> 4 (+4) -> 5
        cfg = graph({0: ("n", [1]), 1: ("n", [2, 4]), 2: ("p", [3]), 3: ("p", [5]), 4: ("p", [5]), 5: ("n", [])},
                    {"start": 0})
        self.assertEqual(self.reach(cfg, {2: add(2), 3: add(3), 4: add(4)}, 5), (4.0, 5.0))

    def test_call_summary_and_optional_side_trip(self):
        # 0 start -> 1 call L -> 2 (side trip M) -> 3 target;  L = 4 (+2) -> 5 return;  M = 6 (+3) -> 7 return
        cfg = graph({0: ("n", [1]), 1: ("c", [2], "L"), 2: ("n", [3]), 3: ("n", []), 4: ("p", [5]), 5: ("r", []),
                     6: ("p", [7]), 7: ("r", [])}, {"start": 0, "L": 4, "M": 6})
        self.assertEqual(self.reach(cfg, {4: add(2), 6: add(3)}, 3, side={2: ["M"]}), (2.0, 5.0))

    def test_side_trip_that_runs_into_the_story_adds_nothing(self):
        from unittest import mock
        # 0 start -> 1 (hands label M over as data) -> 2 target;  M = 3 (+5) -> 4 -> 5 -> 6 -> 7 return, far away
        cfg = graph({0: ("n", [1]), 1: ("n", [2]), 2: ("n", []), 3: ("p", [4]), 4: ("n", [5]), 5: ("n", [6]),
                     6: ("n", [7]), 7: ("r", [])}, {"start": 0, "M": 3})
        with mock.patch.object(rpw, "SUBROUTINE_REACH", 2):
            self.assertEqual(self.reach(cfg, {3: add(5)}, 2, side={1: ["M"]}), (0.0, 0.0))
        self.assertEqual(self.reach(cfg, {3: add(5)}, 2, side={1: ["M"]}), (0.0, 5.0))  # its return is near

    def test_loop_counts_each_gain_once(self):
        # hub 1 -> 2 (+1) -> 1;  hub -> 3 (+1) -> 1;  hub -> 4 target
        cfg = graph({0: ("n", [1]), 1: ("n", [2, 3, 4]), 2: ("p", [1]), 3: ("p", [1]), 4: ("n", [])}, {"start": 0})
        self.assertEqual(self.reach(cfg, {2: add(1), 3: add(1)}, 4), (0.0, 2.0))

    def test_reset_overrides_earlier_gains(self):
        cfg = graph({0: ("n", [1]), 1: ("p", [2]), 2: ("p", [3]), 3: ("n", [])}, {"start": 0})
        self.assertEqual(self.reach(cfg, {1: add(5), 2: (rpw.NEG, 1.0)}, 3), (1.0, 1.0))

    def test_unused_respects_calls_and_returns(self):
        # main: 0 start -> 1 (+1) -> 2 call R -> 3 read -> 4 (+1) -> 5 call R -> 6 end
        # R: 7 (+1) -> 8 return.  The gain inside R is followed by the read after the first call.
        cfg = graph({0: ("n", [1]), 1: ("p", [2]), 2: ("c", [3], "R"), 3: ("n", [4]), 4: ("p", [5]),
                     5: ("c", [6], "R"), 6: ("r", []), 7: ("p", [8]), 8: ("r", [])}, {"start": 0, "R": 7})
        d = {"callscreens": [], "showscreens": [], "screens": [], "reads": [], "defines": []}
        ordered = [("s.rpy", 1, "set", "x += 1"), ("s.rpy", 3, "if", "x > 1"), ("s.rpy", 4, "set", "x += 1"),
                   ("s.rpy", 7, "set", "x += 1")]
        with tempfile.TemporaryDirectory() as work:
            unused, off = rpw.unused_sets(work, d, cfg, ordered)
        self.assertEqual((unused, off), ({("s.rpy", 4)}, 0))

    def test_flags_keep_correlated_branches_apart(self):
        # menu 1: 2 sets escort = 1 and +1, or 3 nothing; then 4 `if escort == 1` -> 5 (+2) or 6; 7 target
        cfg = graph({0: ("n", [1]), 1: ("n", [2, 3]), 2: ("p", [4]), 3: ("n", [4]), 4: ("n", [5, 6]), 5: ("p", [7]),
                     6: ("n", [7]), 7: ("n", [])}, {"start": 0})
        cfg["nodes"][4].append([[["escort == 1", True]], [["escort == 1", False]]])
        flags = rpw.Flags(["escort"], [0], {2: [(0, 1)]}, [set(range(8))])
        flow = rpw.StoryFlow(cfg, {2: add(1), 5: add(2)}, {}, None, flags)
        arrive = rpw.at_nodes(flow.solve([flow.state(0)], True)[0], {7})
        self.assertEqual(dict((val, rpw.apply_fn(f, 0.0)) for val, f in arrive.items()), {(1,): 3.0, (0,): 0.0})
        self.assertEqual(self.reach(cfg, {2: add(1), 5: add(2)}, 7), (0.0, 3.0))

    def test_flag_truth_is_three_valued(self):
        flags = rpw.Flags(["a", "b"], [True, False])
        self.assertIs(flags.truth("a and not b", (True, False)), True)
        self.assertIs(flags.truth("a == 1 or other", (True, rpw.UNKNOWN)), True)
        self.assertIsNone(flags.truth("b and other", (rpw.UNKNOWN, True)))
        self.assertIs(flags.truth("b and other", (True, False)), False)
        self.assertIs(flags.truth("store.a in (1, 2)", (2, False)), True)

    def test_repeatable_gains_in_unguarded_loop(self):
        # hub 1 -> 2 (+1) -> 1; hub -> 3 target. Nothing stops 2 from running again.
        cfg = graph({0: ("n", [1]), 1: ("n", [2, 3]), 2: ("p", [1]), 3: ("n", [])}, {"start": 0})
        flow = rpw.StoryFlow(cfg, {2: add(1)}, {})
        _state_in, adj, loops = flow.solve([flow.state(0)], True)
        self.assertEqual(rpw.repeatable_gains(adj, loops, {2: add(1)}, {3}), {2})

    def test_flow_edges_from_hints(self):
        with tempfile.TemporaryDirectory() as work:
            with open(os.path.join(work, "hints.py"), "w") as f:
                f.write('FLOW_EDGES = {"credits.rpy:5": "main12", "a.rpy:9": ["x", "y"]}\n')
            self.assertEqual(rpw.load_flow_edges(work), {"credits.rpy:5": ["main12"], "a.rpy:9": ["x", "y"]})

    def test_screen_labels(self):
        text = 'textbutton "Go" action Jump("day2")\ntimer 1 action Jump(timer_jump)\n' \
               'timer 0.1 action Jump("main" + str(ep))\nimagebutton action Function(store.addclick)\n' \
               'textbutton "Bonus" action Call("bonus")'
        jumps, calls = rpw.screen_labels(text, {"timer_jump": "fail", "ep": "12"}, {"addclick": ({"win"}, set())})
        self.assertEqual((jumps, calls), ({"day2", "fail", "main12", "win"}, {"bonus"}))


def py_read(line, code):
    return {"file": "s.rpy", "line": line, "kind": "python", "code": code}


def if_read(line, code):
    return {"file": "s.rpy", "line": line, "kind": "if", "code": code}


def guarded(cond):
    return [[[cond, True]], [[cond, False]]]


PTS_DEFAULT = {"file": "s.rpy", "line": 0, "kind": "default", "name": "pts", "code": "0"}


class StoryEdgeCaseTest(unittest.TestCase):
    """Story-graph cases that once gave too narrow a range or a false "unused so far"."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rpw-graph-")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def world(self, src, nodes, labels, reads, defines=(PTS_DEFAULT,), callscreens=(), screens=()):
        os.makedirs(os.path.join(self.tmp, "src"))
        with open(os.path.join(self.tmp, "src", "s.rpy"), "w") as f:
            f.write(src)
        d = {"reads": list(reads), "defines": list(defines), "callscreens": list(callscreens), "showscreens": [],
             "screens": list(screens), "menus": [], "labels": []}
        return d, {"files": ["s.rpy"], "labels": labels, "nodes": nodes}

    def budget(self, d, cfg, ref, via=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rpw.flow_range(self.tmp, d, cfg, "pts", None, ref, 0.0, via)
        return out.getvalue()

    def test_call_button_gains_count_after_the_screen(self):
        src = ('label start:\n    call screen pick\n    if pts >= 1:\n        "yes"\n    return\nscreen pick:\n'
               '    textbutton "A" action Call("bonus")\nlabel bonus:\n    $ pts += 1\n    return\n')
        nodes = [[0, 1, "n", [1], None], [0, 2, "n", [2], None], [0, 3, "n", [3, 4], None, guarded("pts >= 1")],
                 [0, 4, "n", [4], None], [0, 5, "r", [], None], [0, 8, "n", [6], None], [0, 9, "p", [7], None],
                 [0, 10, "r", [], None]]
        d, cfg = self.world(src, nodes, {"start": 0, "bonus": 5}, [py_read(9, "pts += 1"), if_read(3, "pts >= 1")],
                            callscreens=[{"file": "s.rpy", "line": 2, "code": "call screen pick"}],
                            screens=[{"name": "pick", "file": "s.rpy", "line": 6}])
        self.assertIn(": 0 to 1 (start 0)", self.budget(d, cfg, "s.rpy:3"))
        ordered = [("s.rpy", 9, "set", "pts += 1"), ("s.rpy", 3, "if", "pts >= 1")]
        self.assertEqual(rpw.unused_sets(self.tmp, d, cfg, ordered), (set(), 0))

    def test_branching_python_changes_are_optional(self):
        code = "if met:\n    pts += 5\nelse:\n    pts -= 2"
        nodes = [[0, 1, "n", [1], None], [0, 2, "p", [2], None], [0, 7, "n", [3, 4], None, guarded("pts >= 3")],
                 [0, 8, "n", [4], None], [0, 9, "r", [], None]]
        d, cfg = self.world("label start:\n", nodes, {"start": 0}, [py_read(2, code), if_read(7, "pts >= 3")])
        self.assertIn(": -2 to 5 (start 0)", self.budget(d, cfg, "s.rpy:7"))

    def test_flag_set_in_a_function_is_not_followed(self):
        src = ('init python:\n    def set_met():\n        global met\n        met = True\ndefault met = False\n'
               'label start:\n    $ set_met()\n    if met:\n        $ pts += 3\n    if pts >= 3:\n        "x"\n    return\n')
        nodes = [[0, 1, "n", [], None], [0, 1, "p", [], None], [0, 5, "n", [], None], [0, 6, "n", [4], None],
                 [0, 7, "p", [5], None], [0, 8, "n", [6, 7], None, guarded("met")], [0, 9, "p", [7], None],
                 [0, 10, "n", [8, 9], None, guarded("pts >= 3")], [0, 11, "n", [9], None], [0, 12, "r", [], None]]
        reads = [py_read(1, "def set_met():\n    global met\n    met = True"), py_read(7, "set_met()"),
                 if_read(8, "met"), py_read(9, "pts += 3"), if_read(10, "pts >= 3")]
        met = {"file": "s.rpy", "line": 5, "kind": "default", "name": "met", "code": "False"}
        d, cfg = self.world(src, nodes, {"start": 3}, reads, defines=(PTS_DEFAULT, met))
        self.assertIn(": 0 to 3 (start 0)", self.budget(d, cfg, "s.rpy:10"))

    def test_label_both_called_and_jumped_returns_to_its_caller(self):
        nodes = [[0, 1, "n", [1], None], [0, 2, "n", [2, 5], None, [[], []]], [0, 4, "c", [3], "bonus"],
                 [0, 5, "n", [4, 6], None, guarded("pts >= 1")], [0, 6, "n", [6], None], [0, 8, "n", [7], None],
                 [0, 9, "r", [], None], [0, 10, "n", [8], None], [0, 11, "p", [9], None], [0, 12, "r", [], None]]
        d, cfg = self.world("label start:\n", nodes, {"start": 0, "bonus": 7},
                            [py_read(11, "pts += 1"), if_read(5, "pts >= 1")])
        ordered = [("s.rpy", 11, "set", "pts += 1"), ("s.rpy", 5, "if", "pts >= 1")]
        self.assertEqual(rpw.unused_sets(self.tmp, d, cfg, ordered), (set(), 0))

    def test_via_inside_a_called_label_continues_after_the_return(self):
        nodes = [[0, 1, "n", [1], None], [0, 2, "c", [2], "date"], [0, 3, "n", [3, 4], None, guarded("pts >= 1")],
                 [0, 4, "n", [4], None], [0, 5, "r", [], None], [0, 6, "n", [6], None],
                 [0, 7, "n", [7, 8], None, [[], []]], [0, 9, "p", [9], None], [0, 11, "n", [9], None],
                 [0, 12, "r", [], None]]
        d, cfg = self.world("label start:\n", nodes, {"start": 0, "date": 5},
                            [py_read(9, "pts += 1"), if_read(3, "pts >= 1")])
        self.assertIn("through s.rpy:9: 1 to 1 (start 0)", self.budget(d, cfg, "s.rpy:3", via="s.rpy:9"))

    def test_elif_read_belongs_to_its_if(self):
        src = 'label start:\n    $ pts += 1\n    if x:\n        "a"\n    elif pts >= 1:\n        "b"\n    return\n'
        nodes = [[0, 1, "n", [1], None], [0, 2, "p", [2], None],
                 [0, 3, "n", [3, 4, 5], None, [[["x", True]], [["x", False], ["pts >= 1", True]],
                                               [["x", False], ["pts >= 1", False]]]],
                 [0, 4, "n", [5], None], [0, 6, "n", [5], None], [0, 7, "r", [], None]]
        d, cfg = self.world(src, nodes, {"start": 0}, [py_read(2, "pts += 1"), if_read(5, "pts >= 1")])
        ordered = [("s.rpy", 2, "set", "pts += 1"), ("s.rpy", 5, "if", "pts >= 1")]
        self.assertEqual(rpw.unused_sets(self.tmp, d, cfg, ordered), (set(), 0))
        self.assertEqual(rpw.statement_nodes(cfg, "s.rpy:5", self.tmp), [2])


if __name__ == "__main__":
    unittest.main()
