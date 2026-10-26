#!/usr/bin/env python3
"""renpy-walkthrough helper: inventory a Ren'Py game's choices through its own engine,
then generate, check, verify and install an in-game walkthrough patch.

Usage (run with `python3 -I`):
    rpw.py locate  <game> [--work DIR]       find base/game dirs, engine, lint command; write DIR/game.json
    rpw.py dump    <game|DIR> [--work DIR]   run the engine dumper via lint -> DIR/rpw_dump.json + lint baseline
    rpw.py extract <DIR>                     copy the game's scripts (.rpa contents, loose .rpy/.rpyc) into DIR/src; dump runs it
    rpw.py recon   <DIR>                     summary + verdict (menu-driven / mixed / custom-choice-system)
    rpw.py list    <DIR> [--file GLOB] [--label NAME] [--group] one row per menu item (TSV); @name rows for list screens
    rpw.py show    <DIR> <FILE:LINE|@list> [--source N] [--reads N]   one menu: items, outlines, effects, reads
    rpw.py budget  <DIR> <VAR> [--before F:L [--via F:L] [--gain RE]]   changes and reads of a points variable; range at a threshold
    rpw.py gen     <DIR>                     DIR/hints.py + dump -> DIR/walkthrough.rpy
    rpw.py check   <DIR> [--only GLOBS]      table vs dump, coverage of SCOPE, hint style
    rpw.py verify  <DIR> [--negative] [--keep] [--no-render]    lint with the patch, self-check, lint diff, render one menu
    rpw.py preview <DIR> <FILE:LINE|@list> [--setup CODE]       boot the game, show that menu (or `call screen` site) with hints, save a PNG
    rpw.py migrate <DIR> [--write]           after a game update + re-dump: move hint keys whose menus moved
    rpw.py spotcheck <DIR> [--sample N] | --compare   blind second opinion on a sample of hints (agent-driven)
    rpw.py update  <DIR>                     uninstall, re-dump, migrate, check; then gen, verify, install if clean
    rpw.py readme  <DIR> [--force] [--notes TEXT]               write DIR/README.md (coverage, not covered, commands)
    rpw.py install <DIR> | uninstall <DIR>

<game> is a macOS .app, a folder containing game/, a launcher .sh, or a .zip (unpacked next to the zip, or --extract-to).
The default DIR is ~/renpy-walkthroughs/<slug>.
"""
import argparse
import contextlib
try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
import hashlib
import ast
import fnmatch
import glob
import io
import json
import os
import plistlib
import re
import runpy
import shutil
import signal
import struct
import subprocess
import sys
import time
import zipfile
import zlib
import pickle

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(SKILL_DIR, "assets")
DUMPER = "_rpw_dump.rpy"
PREVIEW = "_rpw_preview.rpy"
TUNE = "screen_choice.rpy"
PREVIEW_TIMEOUT = 60
GAME_EXIT_TIMEOUT = 20  # seconds to wait for a killed or finished game process
PATCH = "walkthrough.rpy"
WORK_ROOT = os.path.expanduser("~/renpy-walkthroughs")
LINT_TIMEOUT = 900
LOCK_DIR = os.path.join(WORK_ROOT, ".locks")
# No audio device (parallel runs deadlock in CoreAudio); on macOS run as a background app so SDL
# never activates the game window (open -g alone still lets some engines take focus).
ENGINE_ENV = {"SDL_AUDIODRIVER": "dummy", "SDL_MAC_BACKGROUND_APP": "1"}
HINT_MAX_LEN = 60
NOTE_MAX_LEN = 90
KINDS = ("good", "bad", "info")
DEFAULT_ANY = "Any choice: dialogue only."
ORIGIN = {}
SELFCHECK_RE = re.compile(r"^walkthrough: (\d+) entries, (\d+) mismatches; wrapped (.*)$")
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][\w.]*(?:\[[^\]]+\])?)\s*(\+|-|\*|/)?=(?!=)\s*(.+)$")
CFG = "rpw_cfg.json"
LABEL_REF_RE = re.compile(r"""\b(Jump|Call|renpy\.jump|renpy\.call|renpy\.call_in_new_context)\(\s*u?['"]([\w.]+)['"]\s*[,)]""")
STRING_LITERAL_RE = re.compile(r"""u?(['"])((?:\\.|(?!\1).)*)\1""")
VAR_ACTION_RE = re.compile(r"\b(Jump|Call)\(\s*(?:store\.)?([A-Za-z_]\w*)\s*[,)]")
CONCAT_ACTION_RE = re.compile(r"""\b(Jump|Call)\(\s*u?['"]([\w.]+)['"]\s*\+\s*(?:str\(\s*)?(?:store\.)?([A-Za-z_]\w*)""")
FUNCTION_ACTION_RE = re.compile(r"\bFunction\(\s*(?:store\.)?([A-Za-z_]\w*)")
STRING_RE = re.compile(r"""u?['"]([\w.]+)['"]""")
STANDARD_SCREENS = {"main_menu", "game_menu", "navigation", "preferences", "save", "load", "file_slots", "confirm",
                    "quick_menu", "history", "help", "about", "say", "input", "nvl", "notify", "skip_indicator",
                    "choice", "ctc", "keyboard_help", "mouse_help", "gamepad_help"}
CHOICE_SCREEN_RE = re.compile(r"choice|menu|decision|option", re.I)
FIXED_SIZE_RE = re.compile(r"\b(xysize|ysize|ymaximum|maximum)\b")
POINTS_RE = re.compile(r"[+-]\d")
SCENE_RE = re.compile(r"\b(scene|gallery)\b", re.I)
COPY_RE = re.compile(r"^\s*[\w]+\.[\w.]+\s*=\s*[\w.]+\s*$")
GALLERY_LINE_RE = re.compile(r"gallery|(?<![\w.])replay", re.I)  # not _in_replay / end_replay
BUTTON_RE = re.compile(r"\b(textbutton|imagebutton|button)\b")
CHOICE_ACTION_RE = re.compile(r"\b(Return|Jump|Call)\(")
QUOTED_RE = re.compile(r"[\"']([A-Za-z_]\w*)[\"']")


def die(msg):
    sys.exit("rpw: " + msg)


def read_text(path, encoding="utf-8", errors="strict"):
    with open(path, encoding=encoding, errors=errors) as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------- locate

def slugify(name):
    """Work-dir name for a game path: `Ripples-0.9.22-mac.zip` -> `ripples`. Platform and version suffixes are
    dropped, so a game update keeps its work dir; a name with no Latin letters gets a stable hash."""
    base = os.path.basename(name.rstrip("/"))
    name = re.sub(r"\.(app|zip|sh|exe)$", "", base, flags=re.I)
    name = re.sub(r"[-_ ](mac|pc|linux|win(dows)?|market|dist|release)\b.*$", "", name, flags=re.I)
    name = re.sub(r"[-_ ]v?\d+(\.\d+)+[a-z]?$", "", name, flags=re.I)
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "game-" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]


def zip_skipped(name):
    """macOS resource forks (__MACOSX/) and dot files: not part of the game."""
    top = name.split("/")[0]
    return top == "__MACOSX" or top.startswith(".")


def zip_tops(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        return sorted({n.split("/")[0] for n in zf.namelist() if n.split("/")[0] and not zip_skipped(n)})


def extract_zip(zip_path, dest):
    """Unpack a game zip into `dest`, unless its top-level entries are already there (then reuse them)."""
    tops = set(zip_tops(zip_path))
    with zipfile.ZipFile(zip_path) as zf:
        files = [i for i in zf.infolist() if not i.is_dir() and not zip_skipped(i.filename)]
    if tops and all(os.path.exists(os.path.join(dest, t)) for t in tops):
        # Same names are not enough: a newer version of the game unpacks to the same folder name.
        differ = [i.filename for i in files if os.path.getsize(os.path.join(dest, i.filename)) != i.file_size]\
            if all(os.path.isfile(os.path.join(dest, i.filename)) for i in files) else ["(missing files)"]
        if differ:
            die("%s differs from the copy already unpacked in %s (e.g. %s): a different version? Move the old folder "
                "away or pass --extract-to" % (zip_path, dest, differ[0]))
        print("already unpacked: %s" % ", ".join(sorted(os.path.join(dest, t) for t in tops)))
        return
    clash = [t for t in tops if os.path.exists(os.path.join(dest, t))]
    if clash:
        die("%s: some entries already exist in %s (%s); move them or pass --extract-to" % (zip_path, dest, clash))
    os.makedirs(dest, exist_ok=True)
    print("unpacking %s into %s ..." % (zip_path, dest))
    with zipfile.ZipFile(zip_path) as zf:
        root = os.path.realpath(dest)
        for info in zf.infolist():
            if zip_skipped(info.filename):
                continue
            target = os.path.realpath(os.path.join(dest, info.filename))
            if not target.startswith(root + os.sep) and target != root:
                die("zip entry escapes the destination: %r" % info.filename)
            zf.extract(info, dest)
            mode = (info.external_attr >> 16) & 0o777
            if mode and not info.is_dir():
                os.chmod(target, mode)


def find_base(path):
    """Return (base dir holding game/ and renpy/, launcher argv prefix)."""
    path = os.path.abspath(path)
    if path.endswith(".sh") and os.path.isfile(path):
        return os.path.dirname(path), ["sh", path]
    if path.endswith(".app"):
        base = os.path.join(path, "Contents", "Resources", "autorun")
        with open(os.path.join(path, "Contents", "Info.plist"), "rb") as f:
            exe = plistlib.load(f)["CFBundleExecutable"]
        return base, [os.path.join(path, "Contents", "MacOS", exe)]
    if os.path.isdir(os.path.join(path, "game")):
        apps = [a for a in os.listdir(path) if a.endswith(".app")]
        if sys.platform == "darwin" and apps:
            return find_base(os.path.join(path, apps[0]))
        shs = [s for s in os.listdir(path) if s.endswith(".sh")]
        if shs:
            return path, ["sh", os.path.join(path, shs[0])]
        die("no launcher (.app or .sh) next to %s/game" % path)
    for dirpath, dirnames, _ in os.walk(path):
        for d in dirnames:
            if d.endswith(".app"):
                return find_base(os.path.join(dirpath, d))
        if "game" in dirnames and "renpy" in dirnames:
            return find_base(dirpath)
    die("no Ren'Py game found under %s" % path)


def engine_info(base):
    renpy_dir = os.path.join(base, "renpy")
    vc = os.path.join(renpy_dir, "vc_version.py")
    version = None
    if os.path.exists(vc):
        text = read_text(vc, errors="replace")
        m = re.search(r"^version\s*=\s*['\"]([^'\"]+)", text, re.M)
        version = m.group(1) if m else "vc_version " + (re.findall(r"\d+", text) or ["?"])[0]
    elif os.path.exists(vc + "o") or os.path.exists(vc + "c"):
        version = "7.x (compiled vc_version only)"
    libs = []
    for libdir in (os.path.join(base, "lib"), os.path.join(base, "..", "lib")):
        if os.path.isdir(libdir):
            libs += os.listdir(libdir)
    py = 2 if any("py2" in l or "python2" in l for l in libs) else 3
    if os.path.exists(vc + "o") and not os.path.exists(vc):
        py = 2
    return version, py


def cmd_locate(args):
    target = args.target
    work = args.work or os.path.join(WORK_ROOT, slugify(target))
    os.makedirs(work, exist_ok=True)
    if target.lower().endswith(".zip"):
        dest = os.path.abspath(getattr(args, "extract_to", None) or os.path.dirname(os.path.abspath(target)))
        tops = zip_tops(target)
        if len(tops) != 1:
            # Loose files or several folders: unpack into their own folder, so the search for the game below
            # can't wander into whatever else sits next to the zip (other games in ~/Downloads).
            dest = os.path.join(dest, os.path.splitext(os.path.basename(target))[0])
        extract_zip(target, dest)
        target = os.path.join(dest, tops[0]) if len(tops) == 1 else dest
    base, launcher = find_base(target)
    game_dir = os.path.join(base, "game")
    if not os.path.isdir(game_dir):
        die("%s has no game/ folder" % base)
    version, py = engine_info(base)
    files = []
    for dirpath, _, names in os.walk(game_dir):
        files += [os.path.relpath(os.path.join(dirpath, n), game_dir) for n in names]
    info = {
        "source": os.path.abspath(args.target),
        "base": base,
        "game_dir": game_dir,
        "lint": launcher + [base, "lint"],
        "engine": version,
        "python": py,
        "rpy": sum(f.endswith(".rpy") and not f.startswith("tl/") for f in files),
        "rpyc": sum(f.endswith(".rpyc") for f in files),
        "rpa": sorted(f for f in files if f.endswith(".rpa")),
    }
    with open(os.path.join(work, "game.json"), "w") as f:
        json.dump(info, f, indent=1)
    for k, v in info.items():
        print("%-9s %s" % (k + ":", " ".join(v) if k == "lint" else v))
    print("%-9s %s" % ("work:", work))
    return work


def load_game(work):
    p = os.path.join(work, "game.json")
    if not os.path.exists(p):
        die("%s missing; run `rpw.py locate <game> --work %s` first" % (p, work))
    return json.loads(read_text(p))


def dumper_hash():
    return hashlib.sha1(read_text(os.path.join(ASSETS, DUMPER)).encode("utf-8")).hexdigest()[:12]


WARNED = set()


def load_dump(work):
    p = os.path.join(work, "rpw_dump.json")
    if not os.path.exists(p):
        die("%s missing; run `rpw.py dump %s` first" % (p, work))
    d = json.loads(read_text(p))
    if d.get("dumper") != dumper_hash() and p not in WARNED:
        WARNED.add(p)
        sys.stderr.write("warning: %s was made by an older dumper; re-run `rpw.py dump %s` for complete outlines\n" % (p, work))
    return d


def resolve_work(arg):
    """Accept a work dir or its slug; return the work dir as an absolute path (the game, which runs
    elsewhere, writes probe and error files into it)."""
    if os.path.exists(os.path.join(arg, "game.json")):
        return os.path.abspath(arg)
    if os.path.isdir(os.path.join(WORK_ROOT, arg)):
        return os.path.join(WORK_ROOT, arg)
    die("%s is not a work dir (no game.json)" % arg)


# ---------------------------------------------------------------- lint runs

@contextlib.contextmanager
def game_lock(game):
    """One engine run per game folder at a time (parallel agents share games)."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    path = os.path.join(LOCK_DIR, hashlib.sha1(game["game_dir"].encode()).hexdigest()[:16] + ".lock")
    with open(path, "w") as f:
        if fcntl is None:
            # Windows: no flock; one rpw run per game at a time is then up to the caller.
            yield
            return
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.stderr.write("waiting for another rpw run on %s ...\n" % game["game_dir"])
            fcntl.flock(f, fcntl.LOCK_EX)
        yield


def engine_env(extra=None):
    """Environment for engine runs: no audio device (parallel runs deadlock in CoreAudio), plus `extra`."""
    env = dict(os.environ, **ENGINE_ENV)
    env.update(extra or {})
    return env


def run_lint(game, report, env_extra=None):
    env = engine_env()
    env.update(env_extra or {})
    cmd = game["lint"] + [report]
    started = time.time()
    try:
        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=LINT_TIMEOUT)
    except subprocess.TimeoutExpired:
        die("lint timed out after %ds: %s" % (LINT_TIMEOUT, " ".join(cmd)))
    sys.stderr.write("lint run: %.0fs\n" % (time.time() - started))
    return p.returncode, p.stdout + p.stderr


def game_listing(game):
    return sorted(os.listdir(game["game_dir"]))


def clean_leftovers(game):
    """Remove files an interrupted rpw run can leave in game/: the dumper and preview scripts, and a
    walkthrough.rpy that is one of verify's deliberately broken test copies (it would run on the next launch)."""
    gd = game["game_dir"]
    for name in (DUMPER, PREVIEW):
        if any(os.path.exists(os.path.join(gd, name + ext)) for ext in ("", "c")):
            remove_compiled(gd, name)
            print("removed a leftover %s from an interrupted run" % name)
    installed = os.path.join(gd, PATCH)
    if os.path.exists(installed):
        text = read_text(installed, errors="replace")
        if "RPW-NEGATIVE " in text or CRASH_COPY in text:
            remove_compiled(gd, PATCH)
            print("removed a leftover test copy of %s; run `rpw.py install` again if it was installed" % PATCH)


def remove_compiled(game_dir, name):
    for ext in ("", "c"):
        p = os.path.join(game_dir, name + ext)
        if os.path.exists(p):
            os.remove(p)


def cmd_dump(args):
    work = args.work
    for cand in (args.target, os.path.join(WORK_ROOT, args.target)):
        if work is None and os.path.exists(os.path.join(cand, "game.json")):
            work = cand
    known = work and os.path.exists(os.path.join(work, "game.json"))
    if known and os.path.exists(args.target) and not os.path.exists(os.path.join(args.target, "game.json")) \
            and os.path.abspath(args.target) != load_game(work).get("source"):
        print("note: %s is not the game %s was made from; locating it again" % (args.target, work))
        known = False
    if not known:
        work = cmd_locate(argparse.Namespace(target=args.target, work=work, extract_to=args.extract_to))
    game = load_game(work)
    gd = game["game_dir"]
    out, pseudo, cfg = os.path.join(work, "rpw_dump.json"), os.path.join(work, "pseudo"), os.path.join(work, CFG)
    with game_lock(game):
        clean_leftovers(game)
        if os.path.exists(os.path.join(gd, PATCH)):
            die("%s is installed; run `rpw.py uninstall %s` first so the lint baseline is the unpatched game"
                % (PATCH, work))
        before = game_listing(game)
        # Write the new dump beside the old one; swap it in only when the run succeeded.
        new_out, new_pseudo, new_cfg = out + ".new", pseudo + ".new", cfg + ".new"
        for path in (new_out, new_cfg):
            if os.path.exists(path):
                os.remove(path)
        shutil.rmtree(new_pseudo, ignore_errors=True)
        os.makedirs(new_pseudo)
        try:
            dump_run(game, gd, work, new_out, new_pseudo, new_cfg)
        except BaseException:  # failed or interrupted: the old dump stays, the half-written new one goes
            for path in (new_out, new_cfg):
                if os.path.exists(path):
                    os.remove(path)
            shutil.rmtree(new_pseudo, ignore_errors=True)
            raise
        if os.path.exists(out):
            # The previous version's dump: `migrate` compares against it after a game update.
            shutil.copy(out, os.path.join(work, "rpw_dump.prev.json"))
        os.replace(new_out, out)
        if os.path.exists(new_cfg):
            os.replace(new_cfg, cfg)
        shutil.rmtree(pseudo, ignore_errors=True)
        os.rename(new_pseudo, pseudo)
        after = game_listing(game)
    if before != after:
        print("warning: game/ listing changed: +%s -%s" % (sorted(set(after) - set(before)), sorted(set(before) - set(after))))
    finish_dump(work, out)
    cmd_extract(argparse.Namespace(work_dir=work))  # DIR/src: show --source, galleries, screen reads


def dump_run(game, gd, work, out, pseudo, cfg):
    shutil.copy(os.path.join(ASSETS, DUMPER), os.path.join(gd, DUMPER))
    try:
        code, log = run_lint(game, os.path.join(work, "lint-baseline.txt"),
                             {"RPW_OUT": out, "RPW_PSEUDO": pseudo, "RPW_CFG": cfg, "RPW_DUMPER_HASH": dumper_hash()})
    finally:
        remove_compiled(gd, DUMPER)
    write_text(os.path.join(work, "lint-baseline-stdout.txt"), log)
    if not os.path.exists(out):
        die("dump failed (lint exit %d); see %s/lint-baseline-stdout.txt\n%s" % (code, work, log[-2000:]))


def finish_dump(work, out):
    d = load_dump(work)
    print("dumped %d menus, %d inputs, %d call-screen sites from %s (engine %s, py%d) -> %s" % (
        len(d["menus"]), len(d["inputs"]), len(d["callscreens"]), d["name"], ".".join(map(str, d["engine"][:3])), d["python"], out))


# ---------------------------------------------------------------- extract (.rpa)

class IndexUnpickler(pickle.Unpickler):
    """An archive index holds only dicts, lists, tuples, numbers and strings: refuse anything that would import
    code (the archive comes from a downloaded game)."""

    def find_class(self, module, name):
        raise pickle.UnpicklingError("archive index refers to %s.%s" % (module, name))


def read_rpa_index(path):
    """{name: [(offset, length, prefix)]} of a Ren'Py archive (RPA-2.0, 3.0, 3.2); ValueError if it isn't one."""
    with open(path, "rb") as f:
        header = f.readline().decode("latin-1")
        parts = header.split()
        try:
            if parts[0] == "RPA-3.0":
                offset, key = int(parts[1], 16), int(parts[2], 16)
            elif parts[0] == "RPA-3.2":
                offset, key = int(parts[1], 16), 0
                for sub in parts[3:]:
                    key ^= int(sub, 16)
            elif parts[0] == "RPA-2.0":
                offset, key = int(parts[1], 16), 0
            else:
                raise ValueError("unsupported archive header %r" % header[:20])
            f.seek(offset)
            index = IndexUnpickler(io.BytesIO(zlib.decompress(f.read())), encoding="bytes").load()
        except (IndexError, zlib.error, pickle.UnpicklingError, EOFError) as e:
            raise ValueError("%s: %s" % (path, e))
    rv = {}
    for name, entries in index.items():
        name = name.decode("utf-8") if isinstance(name, bytes) else name
        rv[name] = [(e[0] ^ key, e[1] ^ key, e[2] if len(e) > 2 else b"") for e in entries]
    return rv


def cmd_extract(args):
    work = resolve_work(args.work_dir)
    game = load_game(work)
    src = os.path.join(work, "src")
    shutil.rmtree(src, ignore_errors=True)  # only extracted files live here; start clean after a game update
    os.makedirs(src)
    root = os.path.realpath(src)
    n = 0
    for rpa in game["rpa"]:
        path = os.path.join(game["game_dir"], rpa)
        try:
            index = read_rpa_index(path)
        except ValueError as e:
            print("warning: skipped %s (%s)" % (rpa, e))
            continue
        with open(path, "rb") as f:
            for name, entries in index.items():
                if not name.endswith((".rpy", ".rpyc")) or name.startswith("tl/"):
                    continue
                dest = os.path.realpath(os.path.join(src, name))
                if not dest.startswith(root + os.sep):
                    die("archive entry escapes the destination: %r" % name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, "wb") as o:
                    for off, length, prefix in entries:
                        if isinstance(prefix, str):
                            prefix = prefix.encode("latin-1")
                        f.seek(off)
                        o.write(prefix + f.read(length - len(prefix)))
                n += 1
    for dirpath, _, names in os.walk(game["game_dir"]):
        for name in names:
            rel = os.path.relpath(os.path.join(dirpath, name), game["game_dir"])
            loose_rpyc = name.endswith(".rpyc") and not os.path.exists(os.path.join(dirpath, name[:-1]))
            if (name.endswith(".rpy") or loose_rpyc) and not rel.startswith("tl/") and name[:len(PATCH)] != PATCH \
                    and not name.startswith("_rpw_"):
                dest = os.path.join(src, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(os.path.join(dirpath, name), dest)
                n += 1
    rpy = sum(1 for _, _, names in os.walk(src) for x in names if x.endswith(".rpy"))
    print("extracted %d script files into %s (%d .rpy)" % (n, src, rpy))
    if rpy == 0:
        print("no .rpy sources: analysis uses the engine dump outlines only")


def source_lines(work, fn):
    """Real source of a script as a list of lines, or None (fn may name the .rpyc)."""
    for cand in (fn, fn[:-1] if fn.endswith(".rpyc") else fn + "x"):
        p = os.path.join(work, "src", cand)
        if cand.endswith(".rpy") and os.path.exists(p):
            return read_text(p, errors="replace").split("\n")
    return None


def source_view(work, fn, start, end):
    """Numbered lines start..end from the real source, else from the dump's pseudo-source."""
    lines = source_lines(work, fn)
    if lines is not None:
        return ["%7d | %s" % (n + 1, lines[n]) for n in range(max(0, start - 1), min(len(lines), end))]
    p = os.path.join(work, "pseudo", fn + ".txt")
    if not os.path.exists(p):
        return None
    out, inside = [], False
    for row in read_text(p).splitlines(True):
        num = row[:7].strip()
        if num.isdigit():  # rows without a number continue the previous statement
            inside = start <= int(num) <= end
        if inside:
            out.append(row.rstrip("\n"))
    return ["(pseudo-source rebuilt from the AST; line numbers match the original .rpy)"] + out


# ---------------------------------------------------------------- recon

def call_target(code):
    m = re.search(r"call screen\s+([\w.]+)|renpy\.call_screen\(\s*['\"]([\w.]+)", code)
    return (m.group(1) or m.group(2)) if m else "?"


def screen_block(lines, line):
    """Source lines of the screen statement starting at `line` (1-based)."""
    start = line - 1
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for s in lines[start + 1:]:
        if s.strip() and len(s) - len(s.lstrip()) <= indent:
            break
        out.append(s)
    return out


def interactive_screen(work, d, name):
    """True when screen `name` has 2+ buttons whose action returns, jumps or calls: a choice outside `menu:`."""
    for scr in d["screens"]:
        if scr["name"] != name or not scr["file"]:
            continue
        block = screen_text(work, scr).split("\n")  # real source, else the pseudo-source (.rpyc-only games)
        buttons = [l for l in block if BUTTON_RE.search(l)]
        actions = sum(1 for l in block if CHOICE_ACTION_RE.search(l))
        return len(buttons) >= 2 and actions >= 2
    return False


def define_value(d, name, depth=3):
    """The literal value of `define/default name = <literal or other name>`, or None."""
    for x in d.get("defines", []):
        if x["name"] == name:
            code = x["code"].strip()
            if re.match(r"^[A-Za-z_][\w.]*$", code) and depth:
                return define_value(d, code, depth - 1)
            try:
                return ast.literal_eval(code)
            except (ValueError, SyntaxError):
                return None
    return None


def choice_style_lines(work, d):
    """Lines of `style choice_button ...:` blocks in the file that defines the choice screen."""
    out = []
    for scr in d["screens"]:
        if scr["name"] != "choice" or not scr["file"]:
            continue
        lines = source_lines(work, scr["file"]) or []
        for n, line in enumerate(lines):
            if re.match(r"^style\s+choice_button\b.*:\s*$", line):
                out += screen_block(lines, n + 1)[1:]
    return out


def hint_chars_estimate(work, d, block):
    """Rough characters per hint line: choice button width over the hint font's average glyph width."""
    width = None
    for line in (block or []) + choice_style_lines(work, d):
        m = re.search(r"\b(xsize|xmaximum|xysize)\s+\(?\s*(\d+)", line)
        if m and not line.strip().startswith("#"):
            width = int(m.group(2))
    from_gui = width is None
    width = width or define_value(d, "gui.choice_button_width")
    size = define_value(d, "gui.choice_button_text_size") or define_value(d, "gui.text_size")
    if not isinstance(width, int) or not isinstance(size, int):
        return None
    for x in d.get("defines", []) if from_gui else []:  # an explicit style xsize has no gui borders
        if x["name"] == "gui.choice_button_borders":
            m = re.match(r"\s*Borders\(\s*(\d+)\s*,\s*\d+\s*,\s*(\d+)", x["code"])
            if m:
                width -= int(m.group(1)) + int(m.group(2))
    return int(width / (max(size - 6, 10) * 0.6))


def button_choice_sets(work, d):
    """`show screen` sites right before a `call screen` that together offer 2+ actionable buttons: choices outside menu:."""
    shows = {}
    for x in d.get("showscreens", []):
        shows.setdefault(x["file"], []).append(x)
    out = []
    for c in d["callscreens"]:
        near = [x for x in shows.get(c["file"], []) if c["line"] - 8 <= x["line"] < c["line"]]
        if not near:
            continue
        names = [call_target(x["code"].replace("show screen", "call screen", 1)) for x in near] + [call_target(c["code"])]
        acting = [n for n in names if screen_actions(work, d, n) >= 1]
        if len(acting) >= 2:
            out.append(("%s:%d" % (c["file"], c["line"]), acting))
    return out


def screen_actions(work, d, name):
    """Number of Jump/Call/Return/SetVariable actions in screen `name`'s source (0 when the source is unavailable)."""
    for scr in d["screens"]:
        if scr["name"] == name and scr["file"]:
            return sum(1 for l in screen_text(work, scr).split("\n") if re.search(r"\b(Return|Jump|Call|SetVariable)\(", l))
    return 0


def cmd_recon(args):
    work = resolve_work(args.work_dir)
    game, d = load_game(work), load_dump(work)
    menus = d["menus"]
    items = [i for m in menus for i in m["items"] if i["choice"]]
    print("game:      %s %s (engine %s, py%d)" % (d["name"], d["version"], ".".join(map(str, d["engine"][:3])), d["python"]))
    print("save dir:  %s" % d["save_directory"])
    src = os.path.join(work, "src")
    n_src = sum(1 for _, _, names in os.walk(src) for x in names if x.endswith(".rpy")) if os.path.isdir(src) else 0
    print("scripts:   %d .rpy, %d .rpyc loose in game/, archives %s; %d .rpy in DIR/src" % (
        game["rpy"], game["rpyc"], game["rpa"] or "none", n_src))
    print("menus:     %d menus, %d choices, %d conditional" % (len(menus), len(items), sum(i["condition"] != "True" for i in items)))
    per_file = {}
    for m in menus:
        per_file[m["file"]] = per_file.get(m["file"], 0) + 1
    for fn in sorted(per_file):
        print("           %3d  %s" % (per_file[fn], fn))
    print("filter:    say_menu_text_filter = %s" % d["say_menu_text_filter"])
    if d["menu_include_disabled"]:
        print("note:      config.menu_include_disabled is set (locked choices are shown)")

    choice = [s for s in d["screens"] if s["name"] == "choice"]
    tune = False
    for s in choice:
        print("choice:    screen choice (variant %s) at %s:%s" % (s["variant"], s["file"], s["line"]))
        block = screen_text(work, s).split("\n") if s["file"] else []
        if not any(l.strip() for l in block):
            print("           (no screen source, neither .rpy nor pseudo-source: run `extract` and `dump`)")
        else:
            hits = [l.strip() for l in block if FIXED_SIZE_RE.search(l)]
            if hits:
                tune = True
                print("           fixed-size lines: %s" % hits[:4])
    for s_ in choice:
        lines = source_lines(work, s_["file"]) if s_["file"] else None
        est = hint_chars_estimate(work, d, screen_block(lines, s_["line"]) if lines else None)
        if est and est < HINT_MAX_LEN:
            print("width:     narrow choice buttons: a hint line fits about %d characters; put HINT_MAX_LEN = %d in hints.py" % (est, est))
    print("hook:      %s" % ("tune mode suggested (fixed-size choice buttons); see reference/tune-mode.md" if tune
                             else "generic wrapper" + ("" if os.path.isdir(os.path.join(work, "src")) else " (run `extract` to check the screen source)")))

    print("inputs:    %d renpy.input sites" % len(d["inputs"]))
    for i in d["inputs"]:
        print("           %s:%d  %s" % (i["file"], i["line"], i["code"].strip()[:90]))
    targets = {}
    for c in d["callscreens"]:
        t = call_target(c["code"])
        targets.setdefault(t, []).append("%s:%d" % (c["file"], c["line"]))
    choice_like = {t: v for t, v in targets.items()
                   if t not in STANDARD_SCREENS and (CHOICE_SCREEN_RE.search(t) or interactive_screen(work, d, t))}
    print("screens:   %d call-screen sites, targets: %s" % (len(d["callscreens"]), ", ".join("%s x%d" % (t, len(v)) for t, v in sorted(targets.items()))))
    if d["pymenus"]:
        print("pymenus:   %d renpy.display_menu sites (not hintable): %s" % (len(d["pymenus"]), ", ".join("%s:%d" % (p["file"], p["line"]) for p in d["pymenus"][:8])))
    list_screens = load_list_screens(work)
    if list_screens:
        lists = list_sets(d, list_screens)
        passed = set(lists)
        stray = [x["name"] for x in d.get("defines", []) if x["name"] not in passed and parse_list_items(x["code"])
                 and any(k in x["code"] for k in ("Choice(",))]
        print("lists:     LIST_SCREENS %s: %d lists at %d call sites%s" % (
            ", ".join(sorted(list_screens)), len(lists), sum(len(v["sites"]) for v in lists.values()),
            "; never passed to a list screen (read directly by other screens?): %s" % ", ".join(stray[:10]) if stray else ""))
    sets = button_choice_sets(work, d)
    if sets:
        print("buttons:   %d choices made of several button screens (no hints possible): %s" % (
            len(sets), "; ".join("%s %s" % (site, "+".join(names)) for site, names in sets[:10])))
    n_custom = sum(len(v) for v in choice_like.values()) + len(d["pymenus"]) + len(sets)
    hintable = len(menus)
    if list_screens:
        listed = sum(len(v) for t, v in choice_like.items() if t in list_screens)
        n_custom -= listed
        hintable += listed
    if hintable < n_custom:
        verdict = "custom-choice-system"
    elif n_custom:
        verdict = "mixed"
    elif list_screens and not menus:
        verdict = "list-driven (LIST_SCREENS)"
    else:
        verdict = "menu-driven"
    if choice_like:
        print("choice-like screens: %s" % ", ".join("%s x%d" % (t, len(v)) for t, v in choice_like.items()))
    print("verdict:   %s" % verdict)
    others = [m for m in menus if other_menu_screen(m)]
    if any(x["name"] == "menu" and "nvl_menu" in x["code"] for x in d.get("defines", [])):
        print("nvl:       `define menu = nvl_menu`: every menu uses the NVL screen; item hints won't show")
    elif others:
        print("screens:   %d menus use another screen (e.g. %s: %s); item hints won't show on them" % (
            len(others), menu_id(others[0]), other_menu_screen(others[0])))
    story_coverage(work, d)


def story_coverage(work, d):
    """Print how many menus the story graph reaches from `start`, and the labels holding the rest: screens or
    computed jumps the graph can't follow lead there, and FLOW_EDGES in hints.py can add the missing links."""
    cfg = load_cfg(work)
    if cfg is None or "start" not in cfg["labels"]:
        return
    load_replay_keys(work)
    g = story_graph(work, d, cfg)
    flow = StoryFlow(cfg, {}, g.jumps, g.side)
    entries = [flow.state(cfg["labels"][x]) for x in ("start", "splashscreen") if x in cfg["labels"]]
    reached = set((cfg["files"][cfg["nodes"][u][0]], cfg["nodes"][u][1])
                  for u, _val in flow.solve(entries, enter_calls=True)[0])
    missed = [m for m in d["menus"] if (m["file"], m["line"]) not in reached and not replay_only(m)]
    sites = [c for ls in list_sets(d, load_list_screens(work)).values() for c in ls["sites"]]
    lists_missed = [c for c in sites if (c["file"], c["line"]) not in reached]
    print("story:     %d of %d menus%s reachable from `start` in the story graph" % (
        len(d["menus"]) - len(missed), len(d["menus"]),
        " and %d of %d list-screen choices" % (len(sites) - len(lists_missed), len(sites)) if sites else ""))
    for c in lists_missed[:5]:
        print("           unreached: %s:%d %s" % (c["file"], c["line"], c["code"][:60]))
    by_label = {}
    for m in missed:
        by_label.setdefault(nearest_label(d, m) or m["label"] or "?", []).append(menu_id(m))
    for name, ids in sorted(by_label.items(), key=lambda kv: -len(kv[1]))[:10]:
        print("           unreached: label %s (%d menus, e.g. %s); add FLOW_EDGES if a screen leads there" % (
            name, len(ids), ids[0]))


# ---------------------------------------------------------------- list / show

def menu_id(m):
    return "%s:%d" % (m["file"], m["line"])


def nearest_label(d, m):
    """The last label at or above the menu in its file (labels without blocks don't enclose anything in the AST)."""
    best = None
    for l in d["labels"]:
        if l["file"] == m["file"] and l["line"] <= m["line"] and (best is None or l["line"] > best["line"]):
            best = l
    return best["name"] if best else None


REPLAY_KEYS = set()


def load_replay_keys(work):
    """Variables a gallery passes through Replay(..., scope={...}); `if <key>` branches then only run in replays."""
    keys = set()
    for _, text in script_texts(work):
        for m in re.finditer(r"Replay\([^\n]*?scope\s*=\s*\{([^}]*)\}", text):
            keys.update(re.findall(r"[\"'](\w+)[\"']\s*:", m.group(1)))
    keys.discard("_in_replay")
    # A key the story itself defines or assigns is an ordinary variable that the gallery also sets.
    dump = os.path.join(work, "rpw_dump.json")
    if keys and os.path.exists(dump):
        d = load_dump(work)
        story = set(x["name"] for x in d.get("defines", []))
        story.update(strip_store(a.group(1)) for r in d["reads"] if r["kind"] == "python"
                     for a in (ASSIGN_RE.match(l) for l in r["code"].split("\n")) if a)
        keys -= story
    REPLAY_KEYS.clear()
    REPLAY_KEYS.update(keys)


def outside_replay(code):
    """Three-valued value of a condition in normal play (`_in_replay` is None, replay-scope keys are 0):
    True, False, or None when it depends on other state."""
    try:
        tree = ast.parse(code.strip(), mode="eval").body
    except SyntaxError:
        return None

    def value(n):
        if isinstance(n, ast.Name) and (n.id == "_in_replay" or n.id in REPLAY_KEYS):
            return False
        if isinstance(n, ast.Constant):
            return bool(n.value)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            v = value(n.operand)
            return None if v is None else not v
        if isinstance(n, ast.BoolOp):
            vals = [value(x) for x in n.values]
            if isinstance(n.op, ast.And):
                return False if False in vals else (True if all(v is True for v in vals) else None)
            return True if True in vals else (False if all(v is False for v in vals) else None)
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            left, right = n.left, n.comparators[0]
            names = [x for x in (left, right) if isinstance(x, ast.Name) and (x.id == "_in_replay" or x.id in REPLAY_KEYS)]
            consts = [x for x in (left, right) if isinstance(x, ast.Constant)]
            if names and consts:
                actual = None if names[0].id == "_in_replay" else 0
                c = consts[0].value
                op = n.ops[0]
                if isinstance(op, (ast.Eq, ast.Is)):
                    return actual == c or (actual in (None, 0, False) and c in (None, 0, False) and isinstance(op, ast.Eq))
                if isinstance(op, (ast.NotEq, ast.IsNot)):
                    return not (actual == c or (actual in (None, 0, False) and c in (None, 0, False) and isinstance(op, ast.NotEq)))
        return None
    return value(tree)


def replay_only(m):
    """True when an enclosing branch can't run in normal play (only during a gallery replay): hints never show there."""
    for _line, tag in m["chain"]:
        cond = None
        if tag.startswith("if ") or tag.startswith("elif "):
            cond = tag.split(" ", 1)[1]
            if outside_replay(cond) is False:
                return True
        elif tag.startswith("else (of if "):
            if outside_replay(tag[len("else (of if "):-1]) is True:
                return True
    return False


def rpyc_text(path):
    """The pickled AST of a .rpyc as text: enough to grep string literals and screen code."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"RENPY RPC2"):
        return zlib.decompress(data).decode("latin-1") if data[:1] == b"x" else ""
    pos = 10
    while pos + 12 <= len(data):
        slot, start, length = struct.unpack("<III", data[pos:pos + 12])
        if slot == 0:
            break
        if slot == 1:
            return zlib.decompress(data[start:start + length]).decode("utf-8", errors="replace")
        pos += 12
    return ""


def script_texts(work):
    """(path relative to game/, text) for every script in DIR/src: .rpy source, or .rpyc AST text when no .rpy exists."""
    src = os.path.join(work, "src")
    for dirpath, _, files in os.walk(src):
        for fn in sorted(files):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src)
            if fn.endswith(".rpy"):
                yield rel, read_text(full, errors="replace")
            elif fn.endswith(".rpyc") and fn[:-1] not in files:
                try:
                    yield rel, rpyc_text(full)
                except (zlib.error, struct.error):
                    continue


def gallery_flags(work):
    """persistent.<name> flags mentioned in gallery code (files calling Replay( or named *gallery*/*replay*)."""
    flags = set()
    d = load_dump(work)
    variables = {x["name"] for x in d.get("defines", [])}
    for rel, text in script_texts(work):
        if "Replay(" in text or GALLERY_LINE_RE.search(os.path.basename(rel)):
            flags.update(re.findall(r"persistent\.(\w+)", text))
            flags.update(q for q in QUOTED_RE.findall(text) if q in variables)
    return flags


def gallery_labels(work, d):
    """Replayable scenes: labels quoted in files that call Replay(), or on any line that mentions a gallery/replay
    (e.g. `CharGallery('Title', 'label', ...)` with `Replay(item.label)` elsewhere)."""
    names = {l["name"] for l in d["labels"]}
    texts = list(script_texts(work))
    if not any("Replay(" in t for _, t in texts):
        return set()
    found = set()
    for _, text in texts:
        if "Replay(" in text:
            found.update(q for q in QUOTED_RE.findall(text) if q in names)
        for line in text.split("\n"):
            if GALLERY_LINE_RE.search(line):
                found.update(q for q in QUOTED_RE.findall(line) if q in names)
    return found


def find_menu(d, ref):
    fn, _, line = ref.rpartition(":")
    for m in d["menus"]:
        if m["line"] == int(line) and (m["file"] == fn or m["file"].endswith("/" + fn)):
            return m
    die("no menu at %s" % ref)


def load_flow_edges(work):
    """FLOW_EDGES from hints.py and fragments: {"file.rpy:LINE": [labels that statement leads to]}, for links the story graph
    can't see (a screen button with a computed target, a jump through a Python function)."""
    edges = merged_setting(work, "FLOW_EDGES")
    return dict((ref, [names] if isinstance(names, str) else list(names)) for ref, names in edges.items())


def load_list_screens(work):
    """LIST_SCREENS from DIR/hints.py: {screen name: {"arg": index, "kwarg": name, "text": attr, "unproxy": [store functions]}}."""
    p = os.path.join(work, "hints.py")
    return runpy.run_path(p).get("LIST_SCREENS", {}) if os.path.exists(p) else {}


def parse_list_items(code):
    """Items of a `define name = [Obj("text", "label", "condition"), ...]` statement, or None if it is not such a list."""
    try:
        node = ast.parse(code.strip(), mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    items = []
    for i, elt in enumerate(node.elts):
        if not isinstance(elt, ast.Call):
            return None
        pos = [a.value if isinstance(a, ast.Constant) else None for a in elt.args]
        kw = {k.arg: (k.value.value if isinstance(k.value, ast.Constant) else None) for k in elt.keywords}
        items.append({"index": i, "caption": kw.get("text", pos[0] if pos else None),
                      "label": kw.get("label", pos[1] if len(pos) > 1 else None),
                      "condition": kw.get("condition", pos[2] if len(pos) > 2 else "True") or "True"})
    return items


def call_arguments(code):
    """The argument text of the first call in a statement: `call screen pick("m1", x) with dissolve` gives
    `"m1", x`. Parentheses inside strings don't count."""
    start = code.find("(")
    if start < 0:
        return ""
    depth, quote = 0, None
    for i in range(start, len(code)):
        ch = code[i]
        if quote:
            if ch == "\\":
                continue
            if ch == quote and code[i - 1] != "\\":
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return code[start + 1:i]
    return ""


def list_sets(d, list_screens):
    """{list name: {"screen", "sites", "define", "items"}} for every call of a list screen with a literal list name."""
    defines = {x["name"]: x for x in d.get("defines", [])}
    out = {}
    for c in d["callscreens"]:
        target = call_target(c["code"])
        cfg = list_screens.get(target)
        if cfg is None:
            continue
        try:
            call = ast.parse("f(%s)" % call_arguments(c["code"]), mode="eval").body
        except SyntaxError:
            continue
        arg = None
        if cfg.get("kwarg"):
            arg = next((k.value for k in call.keywords if k.arg == cfg["kwarg"]), None)
        if arg is None and len(call.args) > cfg.get("arg", 0):
            arg = call.args[cfg.get("arg", 0)]
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        name = arg.value
        entry = out.setdefault(name, {"screen": target, "sites": [], "define": defines.get(name), "items": None,
                                      "attr": cfg.get("text", "text")})
        entry["sites"].append(c)
        if entry["define"]:
            entry["items"] = parse_list_items(entry["define"]["code"])
    return out


SUBROUTINE_REACH = 400  # statements from a called label's entry within which its returns go back to the caller
READ_KINDS = ("if", "while", "menu-if", "src-if", "read", "choice-if")


def file_order_unused(ordered):
    """Sets after the last read in file order (dumps without a story graph), and no off-graph count."""
    reads_at = [i for i, r in enumerate(ordered) if r[2] in READ_KINDS]
    last = reads_at[-1] if reads_at else -1
    return set((r[0], r[1]) for i, r in enumerate(ordered) if r[2] == "set" and i > last), 0


def unused_sets(work, d, cfg, ordered):
    """(set of (file, line) of changes that no story read can follow, number of reads outside the story graph).
    Calls are stepped over and count as reads when the called label (or anything it calls) reads the variable; a
    label's returns lead back to its callers, which matters only for changes inside the called label."""
    g = story_graph(work, d, cfg)
    nodes, labels, at = g.nodes, g.labels, g.at
    radj = g.predecessors(enter_calls=False)
    called = g.callers()
    reads, off_graph = set(), 0
    sites = None
    for fn, line, kind, code in ordered:
        if kind not in READ_KINDS:
            continue
        found = list(at.get((fn, line), ()))
        if not found and kind in ("if", "src-if"):
            cond = re.sub(r"^\s*(el)?if\s+|:\s*$", "", code) if kind == "src-if" else code
            owner = guard_owner(cfg, fn, line, cond)
            found = [owner] if owner is not None else []
        if kind == "choice-if":  # a list item's condition is read where the list screen is called
            if sites is None:
                sites = list_sets(d, load_list_screens(work))
            entry = sites.get(code.split(":", 1)[0].lstrip("@"))
            found = [u for c in (entry["sites"] if entry else ()) for u in at.get((c["file"], c["line"]), ())]
        if found:
            reads.update(found)
        else:
            off_graph += 1
    def close(seen, frontier):
        while frontier:
            u = frontier.pop()
            if u not in seen:
                seen.add(u)
                frontier.extend(radj[u])

    # 1. Statements that reach a read without returning; a call reaches one when its label does.
    before_read, grew = set(), True
    close(before_read, list(reads))
    while grew:
        sites = [c for name, cs in called.items() if labels[name] in before_read for c in cs if c not in before_read]
        grew = bool(sites)
        close(before_read, sites)
    # 2. Statements inside a called label also reach the reads that follow its callers.
    grew = True
    while grew:
        rets = [r for name, cs in called.items() if any(v in before_read for c in cs for v in nodes[c][3])
                for r in g.own_returns(name) if r not in before_read]
        grew = bool(rets)
        close(before_read, rets)
    unused = set()
    for fn, line, kind, _code in ordered:
        if kind == "set" and (fn, line) in at:
            # a read in the same statement (x += 1 if x < 3 ...) is not after it; its successors decide
            after = [v for u in at[(fn, line)] for v in g.flow(u)]
            if not any(v in before_read for v in after):
                unused.add((fn, line))
    return unused, off_graph


def budget_rows(work, d, var, src_ifs=True):
    """(file, line, kind, code) rows for every change and read of VAR (a name, or a regex for method-based
    systems), sorted with define/default first, then file order. `src_ifs` adds `if` lines found only in DIR/src
    (screens), which the dump doesn't index."""
    plain = re.match(r"^[A-Za-z_][\w.]*$", var) is not None
    pat = re.compile(r"(?:(?<![\w.])|(?<![\w.])store\.)%s\b" % re.escape(strip_store(var)) if plain else var)
    rows = []
    for r in d["reads"]:
        if not pat.search(r["code"]):
            continue
        if r["kind"] == "python":
            for line in r["code"].split("\n"):
                a = ASSIGN_RE.match(line)
                if a and (strip_store(a.group(1)) == strip_store(var) or (not plain and pat.match(a.group(1)))):
                    rows.append((r["file"], r["line"], "set", "%s %s= %s" % (var, a.group(2) or "", a.group(3))))
                elif pat.search(line):
                    rows.append((r["file"], r["line"], "read", line.strip()))
        else:
            rows.append((r["file"], r["line"], r["kind"], r["code"].strip()))
    for x in d.get("defines", []):
        if x["name"] == var or (not plain and pat.search(x["name"])):
            rows.append((x["file"], x["line"], x["kind"], "%s = %s" % (x["name"], x["code"].strip())))
        elif pat.search(x["code"]) and parse_list_items(x["code"]):
            rows.append((x["file"], x["line"], "choice-if", "@%s: %s" % (x["name"], " ".join(x["code"].split())[:100])))
    seen = {(r[0], r[1]) for r in rows}
    if plain and src_ifs:
        for rel, text in script_texts(work):
            if not rel.endswith(".rpy"):
                continue
            for n, line in enumerate(text.split("\n"), 1):
                if (rel, n) not in seen and re.match(r"\s*(if|elif|showif)\b", line) and pat.search(line):
                    rows.append((rel, n, "src-if", line.strip()))
    return sorted(set(rows), key=lambda r: (r[2] not in ("define", "default"), natural_key(r[0]), r[1]))


def unused_claims(work, d, table):
    """Warnings for item hints that call a stat unused ("not used yet", "unused", ...) while a story read of a
    variable that item changes can follow it. Only the claim's own part of the hint counts: in
    "Assertive +1 · Krystal lust +1 (not used yet)" only Krystal's variable is tested."""
    cfg = load_cfg(work)
    if cfg is None:
        return []
    menus = dict(((m["file"], m["line"]), m) for m in d["menus"])
    letters = lambda t: re.sub(r"[^a-z]", "", t.lower())
    cache, out = {}, []
    for key, e in sorted(table.items()):
        m = menus.get(key)
        for idx, (_cap, _kind, text) in sorted(e["items"].items()) if m else ():
            parts = text.split(u" \u00b7 ")
            claim = [p for p in parts if UNUSED_RE.search(p)]
            if not claim:
                continue
            changed = sorted(set((o[1], v) for o in m["items"][idx]["outline"] if o[2] == "python"
                                 for v, op, _ in assigned_vars(o[3]) if op in ("+=", "-=")))
            named = lambda seg: [(l, v) for l, v in changed if letters(v.split(".")[-1]) in letters(seg)]
            # the variables the claim names, else those the hint names anywhere, else all the item changes
            tested = named(" ".join(claim)) or named(text) or changed
            for line, var in tested:
                if var not in cache:
                    cache[var] = unused_sets(work, d, cfg, budget_rows(work, d, var, src_ifs=False))[0]
                if (key[0], line) not in cache[var]:
                    out.append("%s:%d[%d]: the hint says %r, but a story read of %s can follow (rpw.py budget %s)"
                               % (key[0], key[1], idx, claim[0], var, var))
    return out


def cmd_budget(args):
    """Every assignment to VAR and every condition that reads it, in file/line order: what a points threshold needs."""
    work = resolve_work(args.work_dir)
    d = load_dump(work)
    plain = re.match(r"^[A-Za-z_][\w.]*$", args.var) is not None
    rows = budget_rows(work, d, args.var)
    ranges = []
    for m in d["menus"]:
        for i in m["items"]:
            lines = [o[1] for o in i["outline"]]
            if i["choice"] and lines:
                ranges.append((m["file"], min(lines), max(lines), "%s[%d]" % (menu_id(m), i["index"])))

    def innermost(fn, line):
        hits = [r for r in ranges if r[0] == fn and r[1] <= line <= r[2]]
        return min(hits, key=lambda r: r[2] - r[1])[3] if hits else ""

    gains = losses = 0
    ordered = rows
    cfg = load_cfg(work)
    unused, off_graph = unused_sets(work, d, cfg, ordered) if cfg else file_order_unused(ordered)
    for fn, line, kind, code in ordered:
        where = innermost(fn, line)
        if kind == "set":
            gains += "+=" in code
            losses += "-=" in code
        late = "   (no read can follow it: unused so far)" if kind == "set" and (fn, line) in unused else ""
        print("%s:%d\t%-7s %s%s%s" % (fn, line, kind, code[:110], "   (choice %s)" % where if where else "", late))
    print("# %d increments, %d decrements, %d threshold reads; files in natural order, which is not always story order" % (
        gains, losses, sum(1 for r in rows if r[2] in ("if", "while", "menu-if"))))
    if cfg is None:
        print("# \"unused so far\" assumes file order is story order; re-run `rpw.py dump` for the story graph")
    elif off_graph:
        print("# %d reads are outside the story (screens, stat pages); they don't count as uses" % off_graph)
    if not args.before:
        return
    gain = re.compile(args.gain) if args.gain else None
    if gain and gain.groups < 1:
        die("--gain needs a group capturing the amount, e.g. 'Noelle\\.pointch\\((-?\\d+)'")
    if cfg is None:
        print("# no %s (dumped before the story graph existed); re-run `rpw.py dump` for path-aware ranges" % CFG)
    elif plain or gain:
        start = next((float(NUMBER_RE.match(c.split("=", 1)[1]).group(1)) for _f, _l, k, c in ordered
                      if k in ("define", "default") and NUMBER_RE.match(c.split("=", 1)[1])), 0.0)
        if flow_range(work, d, cfg, args.var if plain else None, gain, args.before, start, args.via) or args.via:
            return
    if plain:
        reach_before(ordered, innermost, args.before)
    else:
        print("# --before needs a plain variable name or --gain for method-based gains (e.g. pointch(2))")


def reach_before(ordered, innermost, ref):
    """File-order estimate of the range just before FILE:LINE, for dumps without a story graph: start + unconditional
    changes + per-menu best/worst item. Exclusive story paths are not modelled, so the max can overstate."""
    fn, line = parse_ref(ref)
    start, fixed, per_menu = 0.0, 0.0, {}
    for f, l, kind, code in ordered:
        if (natural_key(f), l) >= (natural_key(fn), line) and kind not in ("define", "default"):
            continue
        m = re.search(r"(\+|-)?=\s*(-?\d+(?:\.\d+)?)\s*$", code)
        if not m:
            continue
        n = float(m.group(2)) * (-1 if m.group(1) == "-" else 1)
        if kind in ("define", "default"):
            start = n
            continue
        if kind != "set" or not m.group(1):
            continue
        where = innermost(f, l)
        if where:
            menu, item = where.rsplit("[", 1)
            per_menu.setdefault(menu, {}).setdefault(item, 0.0)
            per_menu[menu][item] += n
        else:
            fixed += n
    best = sum(max(list(v.values()) + [0.0]) for v in per_menu.values())
    worst = sum(min(list(v.values()) + [0.0]) for v in per_menu.values())
    print("# before %s (file order): start %g, unconditional %+g, %d menus; about %g to %g (paths not modelled)" % (
        ref, start, fixed, len(per_menu), start + fixed + worst, start + fixed + best))


# ---------------------------------------------------------------- budget along story paths
#
# A path's effect on the variable is a function v -> max(v + A, B), stored as (A, B): A is what it adds, B the best
# value it may set. Joining two paths takes the larger A and B; following one path by another composes them.

NEG = float("-inf")
IDENTITY = (0.0, NEG)
UNREACHED = (NEG, NEG)
NUMBER_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")
BIG_LOOP = 50


def then(f, g):
    """Path f followed by path g."""
    return (f[0] + g[0], max(f[1] + g[0], g[1]))


def join(f, g):
    return (max(f[0], g[0]), max(f[1], g[1]))


def apply_fn(f, v):
    return max(v + f[0], f[1])


def loop_fn(effects):
    """A loop of statements: each gain is collected once (visited flags usually stop repeats), after the best reset."""
    gain = sum(e[0] for e in effects if e[0] > 0)
    return (gain, max([e[1] for e in effects] + [NEG]) + gain)


def tarjan(adj):
    """Strongly connected components of {node: [(successor, fn), ...]}, each listed after every component it reaches."""
    index, low, on, stack, comps = {}, {}, set(), [], []
    for root in adj:
        if root in index:
            continue
        work = [(root, 0, None)]
        while work:
            u, i, child = work.pop()
            if child is None and i == 0:
                index[u] = low[u] = len(index)
                stack.append(u)
                on.add(u)
            if child is not None:
                low[u] = min(low[u], low[child])
            succ = adj[u]
            while i < len(succ):
                v = succ[i][0]
                i += 1
                if v not in index:
                    work.append((u, i, v))
                    work.append((v, 0, None))
                    break
                if v in on:
                    low[u] = min(low[u], index[v])
            else:
                if low[u] == index[u]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == u:
                            break
                    comps.append(comp)
    return comps


class Unknown(object):
    """A flag value the analysis can't know (set from an expression, or never given a literal default)."""

    def __repr__(self):
        return "?"


UNKNOWN = Unknown()
MAX_FLAGS = 8
BREAKDOWN_FLAGS = 2
STATES_PER_STATEMENT = 6  # the cap on path states, per statement of the game
FLAG_WALK = 300
COMPARE = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
           ast.LtE: lambda a, b: a <= b, ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
           ast.Is: lambda a, b: a is b, ast.IsNot: lambda a, b: a is not b,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}


def dotted(node):
    """`a.b.c` for a Name/Attribute chain (without a leading `store.`), else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    name = ".".join([node.id] + parts[::-1])
    return name[6:] if name.startswith("store.") else name


class Flags:
    """Literal-valued variables a query follows along each path: their start values, the statements that assign
    them, where a later test can still read them, and three-valued evaluation of if/while/menu conditions."""

    def __init__(self, names=(), start=(), assigns=None, live=None):
        self.names = list(names)
        self.index = dict((n, i) for i, n in enumerate(self.names))
        self.start = tuple(start)
        self.assigns = assigns or {}  # node -> [(flag index, value)]
        self.live = live or []        # per flag: nodes from which a test of it (or the query target) is reachable
        self.parsed = {}

    def assign(self, u, val):
        if u not in self.assigns:
            return val
        val = list(val)
        for i, v in self.assigns[u]:
            val[i] = v
        return tuple(val)

    def prune(self, u, val):
        """Forget flags no later test reads, so paths that differ only in them merge."""
        return tuple(x if u in self.live[i] else UNKNOWN for i, x in enumerate(val)) if self.names else val

    def allows(self, guard, val):
        for cond, want in guard:
            truth = self.truth(cond, val)
            if truth is not None and truth != want:
                return False
        return True

    def truth(self, cond, val):
        """True/False when the tracked flags decide `cond`, else None."""
        if not self.names:
            return None
        if cond not in self.parsed:
            try:
                self.parsed[cond] = ast.parse(cond.strip(), mode="eval").body
            except SyntaxError:
                self.parsed[cond] = None
        node = self.parsed[cond]
        return None if node is None else self.truth_of(node, val)

    def truth_of(self, node, val):
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            inner = self.truth_of(node.operand, val)
            return None if inner is None else not inner
        if isinstance(node, ast.BoolOp):
            parts = [self.truth_of(v, val) for v in node.values]
            decisive = isinstance(node.op, ast.Or)  # `or` is decided by a True part, `and` by a False one
            if decisive in parts:
                return decisive
            return None if None in parts else not decisive
        if isinstance(node, ast.Compare):
            left = self.value_of(node.left, val)
            for op, comp in zip(node.ops, node.comparators):
                right = self.value_of(comp, val)
                if left is UNKNOWN or right is UNKNOWN or type(op) not in COMPARE:
                    return None
                try:
                    if not COMPARE[type(op)](left, right):
                        return False
                except TypeError:
                    return None
                left = right
            return True
        value = self.value_of(node, val)
        return None if value is UNKNOWN else bool(value)

    def value_of(self, node, val):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant):
            return -node.operand.value
        if isinstance(node, (ast.Tuple, ast.List)):
            items = [self.value_of(e, val) for e in node.elts]
            return UNKNOWN if UNKNOWN in items else tuple(items)
        name = dotted(node)
        return val[self.index[name]] if name in self.index else UNKNOWN


NO_FLAGS = Flags()


class TooManyStates(Exception):
    pass


class StoryFlow:
    """The dumper's control-flow graph (rpw_cfg.json) with each statement's effect on one variable. A state is
    (statement, values of the tracked flags); with no flags it is (statement, ())."""

    def __init__(self, cfg, effects, extra, side=None, flags=None):
        self.nodes = cfg["nodes"]
        self.labels = cfg["labels"]
        self.effects = effects  # node index -> fn
        self.extra = extra      # node index -> label names its screen buttons or python jumps lead to
        self.side = side or {}  # node index -> labels it hands to the game as data (read later, e.g. phone messages)
        self.flags = flags or NO_FLAGS
        self.summaries = {}
        self.regions = {}
        self.modified = {}
        self.explored = 0

    def state(self, u, val=None):
        return (u, self.flags.prune(u, self.flags.start if val is None else val))

    def edges(self, st, enter_calls):
        """(successor state, fn on the edge). Edges whose condition the flags rule out are dropped; a call's return
        edges carry the called label's summary; labels handed over as data are optional side trips that return."""
        u, val = st
        node = self.nodes[u]
        kind, succ, target = node[2], node[3], node[4]
        guards = node[5] if len(node) > 5 else None
        val = self.flags.assign(u, val)
        entry = self.labels.get(target) if kind == "c" else None
        exits = self.through(target, val) if entry is not None else {val: IDENTITY}
        for name in self.side.get(u, ()):
            if name in self.labels and name != target:
                both = {}
                for xv, f in exits.items():
                    both[xv] = join(both.get(xv, UNREACHED), f)  # the trip is optional
                    for yv, g in self.through(name, xv, optional=True).items():
                        both[yv] = join(both.get(yv, UNREACHED), then(f, g))
                exits = both
        out = []
        for k, v in enumerate(succ):
            if guards is None or self.flags.allows(guards[k], val):
                out.extend((self.state(v, xv), f) for xv, f in exits.items())
        if enter_calls:  # a threshold inside a called label or side trip is reached by going in
            inner = ([target] if entry is not None else []) + list(self.side.get(u, ()))
            out.extend((self.state(self.labels[t], val), IDENTITY) for t in inner if t in self.labels)
        out.extend((self.state(self.labels[n], val), IDENTITY) for n in self.extra.get(u, ()) if n in self.labels)
        return out

    def solve(self, sources, enter_calls, within=None):
        """({state: best path fn on arrival}, adjacency, {state: size of its loop}) for every state reachable from
        the source states (only through statements in `within`, when given)."""
        adj, stack = {}, list(sources)
        while stack:
            u = stack.pop()
            if u in adj:
                continue
            adj[u] = [e for e in self.edges(u, enter_calls) if within is None or e[0][0] in within]
            stack.extend(v for v, _fn in adj[u] if v not in adj)
            self.explored += 1
            if self.flags.names and self.explored > STATES_PER_STATEMENT * len(self.nodes):
                raise TooManyStates()
        comps = tarjan(adj)
        comp_of = dict((u, ci) for ci, comp in enumerate(comps) for u in comp)
        comp_in = [UNREACHED] * len(comps)
        for u in sources:
            comp_in[comp_of[u]] = IDENTITY
        state_in, loops = {}, {}
        for ci in reversed(range(len(comps))):
            comp, f_in = comps[ci], comp_in[ci]
            cyclic = len(comp) > 1 or any(v == comp[0] for v, _fn in adj[comp[0]])
            if cyclic:
                inner = [self.effects.get(u[0], IDENTITY) for u in comp]
                inner += [fn for u in comp for v, fn in adj[u] if comp_of[v] == ci]
                f_in = then(f_in, loop_fn(inner))
            for u in comp:
                state_in[u] = f_in
                if cyclic:
                    loops[u] = len(comp)
                out = f_in if cyclic else then(f_in, self.effects.get(u[0], IDENTITY))
                for v, fn in adj[u]:
                    if comp_of[v] != ci:
                        comp_in[comp_of[v]] = join(comp_in[comp_of[v]], then(out, fn))
        return state_in, adj, loops

    def through(self, label, val, optional=False):
        """The called label's summary, with the caller's values kept for flags the label never assigns."""
        kept = self.assigned_in(label)
        out = {}
        for xv, f in self.summary(label, val, optional).items():
            xv = tuple(xv[i] if i in kept else val[i] for i in range(len(val)))
            out[xv] = join(out.get(xv, UNREACHED), f)
        return out

    def assigned_in(self, label):
        """Indexes of the flags a label (or anything it jumps to or calls) may assign."""
        if label not in self.modified:
            seen, stack, found = set(), [self.labels[label]], set()
            while stack:
                u = stack.pop()
                if u in seen:
                    continue
                seen.add(u)
                found.update(i for i, _v in self.flags.assigns.get(u, ()))
                n = self.nodes[u]
                stack.extend(n[3])
                stack.extend(self.labels[x] for x in list(self.extra.get(u, ())) + list(self.side.get(u, ()))
                             + ([n[4]] if n[2] == "c" else []) if x in self.labels)
            self.modified[label] = found
        return self.modified[label]

    def region(self, label):
        """Statements within SUBROUTINE_REACH of a label's entry (following flow, stepping over calls): where its own
        `return` must be. A label that runs on into the story only reaches the game's end much later."""
        if label not in self.regions:
            seen, layer = set([self.labels[label]]), [self.labels[label]]
            for _depth in range(SUBROUTINE_REACH):
                nxt = [v for u in layer for v in list(self.nodes[u][3]) + [self.labels[x] for x in self.extra.get(u, ())
                                                                          if x in self.labels] if v not in seen]
                seen.update(nxt)
                if not nxt:
                    break
                layer = nxt
            self.regions[label] = seen
        return self.regions[label]

    def summary(self, label, val, optional=False):
        """{flag values on return: best path fn} through a called label, from its entry to its own returns. An
        optional side trip without one adds nothing (it is a jump into the story, which the story reaches anyway);
        a real `call` then falls back to every return or dead end it can reach."""
        key = (label, val, optional)
        if key in self.summaries:
            return self.summaries[key]
        self.summaries[key] = {val: IDENTITY}  # a recursive call counts as nothing
        state_in, adj, _loops = self.solve([self.state(self.labels[label], val)], False, self.region(label))
        returns = [st for st in state_in if not adj[st] and self.nodes[st[0]][2] == "r"]
        if not returns and optional:
            self.summaries[key] = {}
            return {}
        if not returns:
            state_in, adj, _loops = self.solve([self.state(self.labels[label], val)], enter_calls=False)
            ends = [st for st in state_in if not adj[st]]
            returns = [st for st in ends if self.nodes[st[0]][2] == "r"] or ends
        out = {}
        for st in returns:
            xv = self.flags.assign(st[0], st[1])
            out[xv] = join(out.get(xv, UNREACHED), then(state_in[st], self.effects.get(st[0], IDENTITY)))
        self.summaries[key] = out or {val: IDENTITY}
        return self.summaries[key]


ASSIGN_ANY_RE = re.compile(r"(?<![\w.])(?:store\.)?([A-Za-z_][\w.]*)\s*(?:[-+*/%]|//|\*\*)?=(?!=)")
QUOTED_NAME_RE = re.compile(r"""['"]([A-Za-z_][\w.]*)['"]""")
CONTROL_RE = re.compile(r"^\s*(if|elif|else|for|while|try|except|with|def)\b")
LITERAL_TYPES = (bool, int, float, str, type(None))


def literal_assignments(d):
    """({(file, line): [(name, value or UNKNOWN)]} for plain `name = ...` Python assignments, {name: count},
    names also changed by augmented assignment or inside a function, which the story graph can't place).
    Assignments inside Python control flow count as UNKNOWN."""
    at, count, augmented = {}, {}, set()
    for r in d["reads"]:
        if r["kind"] != "python":
            continue
        lines = r["code"].split("\n")
        branching = any(CONTROL_RE.match(l) for l in lines)
        def_indent = None
        for line in lines:
            indent = len(line) - len(line.lstrip())
            if def_indent is not None and line.strip() and indent <= def_indent:
                def_indent = None
            if re.match(r"\s*def\s", line):
                def_indent = indent
            g = re.match(r"\s*global\s+(.+)$", line)
            if g:
                augmented.update(n.strip() for n in g.group(1).split(","))
            a = ASSIGN_RE.match(line)
            if not a:
                continue
            name = a.group(1)[6:] if a.group(1).startswith("store.") else a.group(1)
            count[name] = count.get(name, 0) + 1
            if a.group(2) or def_indent is not None:
                augmented.add(name)
                continue
            try:
                value = ast.literal_eval(a.group(3).strip())
            except (ValueError, SyntaxError):
                value = UNKNOWN
            if branching or not isinstance(value, LITERAL_TYPES):
                value = UNKNOWN
            at.setdefault((r["file"], r["line"]), []).append((name, value))
    return at, count, augmented


def guard_names(cfg):
    """{node: set of dotted names its edge conditions read}."""
    out, parsed = {}, {}
    for u, n in enumerate(cfg["nodes"]):
        if len(n) < 6:
            continue
        names = set()
        for guard in n[5]:
            for cond, _want in guard:
                if cond not in parsed:
                    try:
                        tree = ast.parse(cond.strip(), mode="eval")
                        parsed[cond] = set(x for x in (dotted(e) for e in ast.walk(tree)) if x)
                    except SyntaxError:
                        parsed[cond] = set()
                names |= parsed[cond]
        if names:
            out[u] = names
    return out


def flag_candidates(work, d, cfg, count, augmented):
    """Names the analysis may follow: every assignment the source text shows is one the story graph sees as a
    plain Python statement or define/default, and nothing names them in a string (SetVariable, setattr)."""
    text_assigns, quoted = {}, set()
    for fn in cfg["files"]:
        for _n, text in source_rows(work, fn):
            for name in ASSIGN_ANY_RE.findall(text):
                text_assigns[name] = text_assigns.get(name, 0) + 1
            quoted.update(QUOTED_NAME_RE.findall(text))
    seen = dict(count)
    for x in d.get("defines", []):
        seen[x["name"]] = seen.get(x["name"], 0) + 1
    return set(n for n, c in text_assigns.items()
               if n not in augmented and n not in quoted and n.split(".")[-1] not in quoted
               and not n.startswith("persistent.") and c <= seen.get(n, 0))


def query_flags(g, interesting, var=None, limit=MAX_FLAGS):
    """The Flags for one query on StoryGraph `g`: up to `limit` candidates whose tests separate branches that reach
    different interesting statements (the variable's changes, the threshold) within FLAG_WALK statements."""
    nodes, d = g.nodes, g.d
    assigns_at, count, augmented = literal_assignments(d)
    tests = guard_names(g.cfg)
    usable = flag_candidates(g.work, d, g.cfg, count, augmented) - set([var])

    def walk(v):
        seen, stack, hits = set(), [v], set()
        while stack and len(seen) < FLAG_WALK:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            if u in interesting:
                hits.add(u)
            stack.extend(g.flow(u))
        return hits

    weight = {}
    for u, names in tests.items():
        names = names & usable
        if not names or len(nodes[u][3]) < 2:
            continue
        reached = [walk(v) for v in nodes[u][3]]
        differ = len(set().union(*reached) - set.intersection(*reached))
        for name in names:
            weight[name] = weight.get(name, 0) + differ
    chosen = [n for n, w in sorted(weight.items(), key=lambda kv: (-kv[1], kv[0])) if w > 0][:limit]
    if not chosen:
        return NO_FLAGS
    index = dict((n, i) for i, n in enumerate(chosen))
    start = [UNKNOWN] * len(chosen)
    for x in d.get("defines", []):
        if x["name"] in index:
            try:
                value = ast.literal_eval(x["code"].strip())
                start[index[x["name"]]] = value if isinstance(value, LITERAL_TYPES) else UNKNOWN
            except (ValueError, SyntaxError):
                pass
    assigns = {}
    for key, pairs in assigns_at.items():
        mine = [(index[name], value) for name, value in pairs if name in index]
        for u in g.at.get(key, ()):
            if mine and nodes[u][2] == "p":
                assigns[u] = mine
    # No return links: a flag set inside a called label is forgotten on return (precision, never paths).
    radj = g.predecessors(enter_calls=True)
    live = []
    for i, name in enumerate(chosen):
        # live = a test of the flag can come next before it is assigned again (the top flags also stay live up to
        # the threshold, for the breakdown by flag value)
        seeds = [u for u, names in tests.items() if name in names]
        seeds += list(interesting) if i < BREAKDOWN_FLAGS else []
        seen, stack = set(), seeds
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            stack.extend(p for p in radj[u] if p not in seen and not any(j == i for j, _v in assigns.get(p, ())))
        live.append(seen)
    return Flags(chosen, start, assigns, live)


def at_nodes(state_in, nodes):
    """{flag values: fn} on arrival at any of `nodes`."""
    out = {}
    for (u, val), f in state_in.items():
        if u in nodes:
            out[val] = join(out.get(val, UNREACHED), f)
    return out


def load_cfg(work):
    path = os.path.join(work, CFG)
    return json.loads(read_text(path)) if os.path.exists(path) else None


def strip_store(name):
    return name[6:] if name.startswith("store.") else name


def var_effects(d, var, gain, sign):
    """({(file, line): fn} for every Python statement that changes the variable, [statements it can't sum]).
    `sign` -1 negates every number, so the same max analysis yields the minimum."""
    out, unknown = {}, []
    for r in d["reads"]:
        if r["kind"] != "python":
            continue
        fn, touched = IDENTITY, False
        lines = r["code"].split("\n")
        # Inside Python if/for/while a change may or may not run: each one is optional.
        step = (lambda f, g: join(f, then(f, g))) if any(CONTROL_RE.match(l) for l in lines) else then
        for line in lines:
            for m in (gain.finditer(line) if gain else ()):
                fn, touched = step(fn, (sign * float(m.group(1)), NEG)), True
            a = ASSIGN_RE.match(line)
            if not var or not a or strip_store(a.group(1)) != var:
                continue
            num = NUMBER_RE.match(a.group(3))
            if not num or a.group(2) in ("*", "/"):
                unknown.append("%s:%d  %s" % (r["file"], r["line"], line.strip()))
                continue
            n = sign * float(num.group(1))
            fn, touched = step(fn, (n if a.group(2) == "+" else -n, NEG) if a.group(2) else (NEG, n)), True
        if touched:
            out[(r["file"], r["line"])] = fn
    return out, unknown


def arg_words(args):
    """Names in a call's argument text: string literals that are a single name, and bare identifiers outside strings
    (dialogue text passed to a screen is skipped)."""
    words = [m.group(2) for m in STRING_LITERAL_RE.finditer(args) if re.match(r"^[\w.]+$", m.group(2))]
    return words + re.findall(r"[A-Za-z_][\w.]*", STRING_LITERAL_RE.sub(" ", args))


def screen_target(code):
    """The screen a `call screen` / `show screen` statement (or renpy.call_screen / show_screen) names, or None."""
    m = re.search(r"(?:call|show) screen\s+([\w.]+)|renpy\.(?:call|show)_screen\(\s*['\"]([\w.]+)", code)
    return (m.group(1) or m.group(2)) if m else None


_ROWS = {}


def source_rows(work, fn):
    """[(line number or None, text)] of a script: the real source, else the dump's pseudo-source (whose rows keep the
    original line numbers; continuation rows have none)."""
    key = (work, fn)
    if key not in _ROWS:
        lines = source_lines(work, fn)
        if lines is not None:
            _ROWS[key] = [(n + 1, line) for n, line in enumerate(lines)]
        else:
            p = os.path.join(work, "pseudo", fn + ".txt")
            rows = read_text(p).split("\n") if os.path.exists(p) else []
            _ROWS[key] = [(int(r[:7]) if r[:7].strip().isdigit() else None, r[10:]) for r in rows if len(r) > 9]
    return _ROWS[key]


def indented_block(rows, i):
    """rows[i] and the rows indented under it."""
    indent = len(rows[i][1]) - len(rows[i][1].lstrip())
    out = [rows[i][1]]
    for _n, text in rows[i + 1:]:
        if text.strip() and len(text) - len(text.lstrip()) <= indent:
            break
        out.append(text)
    return out


def screen_text(work, scr):
    """Source of screen `scr` (a dump `screens` entry), from the real source or the pseudo-source."""
    rows = source_rows(work, scr["file"])
    pat = re.compile(r"\s*screen\s+%s\b" % re.escape(scr["name"]))
    for i, (n, text) in enumerate(rows):
        if pat.match(text) and (n is None or n >= scr["line"]):
            return "\n".join(indented_block(rows, i))
    return ""


def label_refs(text):
    """(labels jumped to, labels called) by literal Jump/Call actions and renpy.jump/renpy.call in `text`."""
    jumps, calls = set(), set()
    for kind, name in LABEL_REF_RE.findall(text):
        (jumps if kind in ("Jump", "renpy.jump") else calls).add(name)
    return jumps, calls


def function_labels(work, files):
    """{function name: (labels its body jumps to, labels it calls)}, for screen buttons whose action is
    Function(name)."""
    out = {}
    for fn in files:
        rows = source_rows(work, fn)
        for i, (_n, text) in enumerate(rows):
            m = re.match(r"\s*def\s+(\w+)\s*\(", text)
            if m:
                jumps, calls = label_refs("\n".join(indented_block(rows, i)))
                old = out.get(m.group(1), (set(), set()))
                out[m.group(1)] = (old[0] | jumps, old[1] | calls)
    return out


def preceding_values(work, site):
    """{variable: literal} for `var = "text"` / `var = 12` assignments (`$` lines or python blocks) between the label
    above a call-screen site and the site: a screen action Jump(var) or Jump("main" + str(var)) leads to the label
    they name."""
    out = {}
    rows = source_rows(work, site["file"])
    end = next((i for i, r in enumerate(rows) if r[0] is not None and r[0] >= site["line"]), len(rows))
    for _n, text in reversed(rows[:end]):
        if re.match(r"\s*label\s", text):
            break
        m = re.match(r"""\s*(?:\$\s*)?([\w.]+)\s*=\s*(?:u?['"]([\w.]+)['"]|(-?\d+))\s*$""", text)
        if m:
            out.setdefault(m.group(1).split(".")[-1], m.group(2) or m.group(3))
    return out


def screen_labels(text, values, funcs):
    """(labels jumped to, labels called) by a screen's buttons and timers: literal Jump/Call targets, Jump(var) and
    Jump("prefix" + str(var)) resolved with the values set before the call, and Function(name) actions."""
    jumps, calls = label_refs(text)
    for kind, var in VAR_ACTION_RE.findall(text):
        if var in values:
            (jumps if kind == "Jump" else calls).add(values[var])
    for kind, prefix, var in CONCAT_ACTION_RE.findall(text):
        if var in values:
            (jumps if kind == "Jump" else calls).add(prefix + values[var])
    for fn in FUNCTION_ACTION_RE.findall(text):
        f_jumps, f_calls = funcs.get(fn, (set(), set()))
        jumps |= f_jumps
        calls |= f_calls
    return jumps, calls


def node_index(cfg):
    """{(file, line): [graph nodes]} for the loaded story graph (cached on it)."""
    if "_at" not in cfg:
        at = {}
        for i, n in enumerate(cfg["nodes"]):
            at.setdefault((cfg["files"][n[0]], n[1]), []).append(i)
        cfg["_at"] = at
    return cfg["_at"]


def story_graph(work, d, cfg):
    """The StoryGraph for this game, built once per command and cached on the loaded rpw_cfg.json."""
    if "_graph" not in cfg:
        cfg["_graph"] = StoryGraph(work, d, cfg)
    return cfg["_graph"]


class StoryGraph(object):
    """The dumper's control-flow graph (rpw_cfg.json) plus the links rpw adds (screen buttons, Python jumps, side
    trips), so every walk over the story uses the same edges:
    - flow(u): where the story goes next, stepping over calls: the statement's successors and its jumps;
    - runs(u): labels u runs and comes back from (`call`, Call actions, renpy.call, labels handed over as data);
    - predecessors(enter_calls): the reverse of flow, plus the edges into the labels u runs when enter_calls;
    - own_returns(label) and return_targets(): where a called label's returns go back to."""

    def __init__(self, work, d, cfg):
        self.work, self.d, self.cfg = work, d, cfg
        self.nodes, self.labels, self.files = cfg["nodes"], cfg["labels"], cfg["files"]
        self.at = node_index(cfg)
        self.jumps, self.side = flow_jumps(work, d, cfg)
        self._preds, self._own, self._callers, self._ret_to = {}, {}, None, None

    def flow(self, u):
        return list(self.nodes[u][3]) + [self.labels[x] for x in self.jumps.get(u, ()) if x in self.labels]

    def runs(self, u):
        n = self.nodes[u]
        return [t for t in ([n[4]] if n[2] == "c" else []) + list(self.side.get(u, ())) if t in self.labels]

    def callers(self):
        """{label: statements that run it and come back}."""
        if self._callers is None:
            self._callers = {}
            for u in range(len(self.nodes)):
                for t in self.runs(u):
                    self._callers.setdefault(t, []).append(u)
        return self._callers

    def predecessors(self, enter_calls):
        if enter_calls not in self._preds:
            radj = [[] for _ in self.nodes]
            for u in range(len(self.nodes)):
                for v in self.flow(u):
                    radj[v].append(u)
                for t in (self.runs(u) if enter_calls else ()):
                    radj[self.labels[t]].append(u)
            self._preds[enter_calls] = radj
        return self._preds[enter_calls]

    def own_returns(self, label):
        """Returns within SUBROUTINE_REACH statements of a called label's entry (following flow). A label that runs
        on into the story reaches the game's last `return` much later; that one ends the game rather than going
        back to the caller."""
        if label not in self._own:
            entry = self.labels[label]
            seen, layer, found = set([entry]), [entry], []
            for _depth in range(SUBROUTINE_REACH):
                nxt = []
                for u in layer:
                    if self.nodes[u][2] == "r":
                        found.append(u)
                    for v in self.flow(u):
                        if v not in seen:
                            seen.add(v)
                            nxt.append(v)
                if not nxt:
                    break
                layer = nxt
            self._own[label] = found
        return self._own[label]

    def return_targets(self):
        """{return statement: statements its label's callers continue with}."""
        if self._ret_to is None:
            self._ret_to = {}
            for name, sites in self.callers().items():
                after = [v for c in sites for v in self.nodes[c][3]]
                for r in self.own_returns(name):
                    self._ret_to.setdefault(r, set()).update(after)
        return self._ret_to


def flow_jumps(work, d, cfg):
    """({node index: label names}, {node index: label names}). The first: labels a statement reaches outside plain
    jumps and calls: buttons of a called or shown screen (see screen_labels, plus label names in the lists the call
    passes), and renpy.jump in Python. The second: labels run as side trips that come back: Call actions,
    renpy.call in Python, and label names a `call` passes as arguments, which the game runs later (phone messages,
    events)."""
    at = node_index(cfg)
    defines = dict((x["name"], x["code"]) for x in d.get("defines", []))
    screens = dict((s["name"], s) for s in d["screens"] if s["file"])
    labels = cfg["labels"]
    funcs = function_labels(work, cfg["files"])
    out, side = {}, {}
    for site in d["callscreens"] + d.get("showscreens", []):
        scr = screens.get(screen_target(site["code"]))
        names, calls = screen_labels(screen_text(work, scr), preceding_values(work, site), funcs) if scr else (set(), set())
        args = site["code"].split("(", 1)[1] if "(" in site["code"] else ""
        for word in arg_words(args):
            names.update(n for n in STRING_RE.findall(defines.get(word, "")) if n in labels)
            if word in labels:
                names.add(word)
        for u in at.get((site["file"], site["line"]), ()):
            out.setdefault(u, set()).update(names)
            side.setdefault(u, set()).update(calls)
    for r in d["reads"]:
        if r["kind"] == "python":
            jumps, calls = label_refs(r["code"])
            for u in at.get((r["file"], r["line"]), ()):
                out.setdefault(u, set()).update(jumps)
                side.setdefault(u, set()).update(calls)
    for ref, names in load_flow_edges(work).items():
        for u in statement_nodes(cfg, ref, work):
            out.setdefault(u, set()).update(names)
    for i, n in enumerate(cfg["nodes"]):
        if n[2] == "c":
            row = next((t for num, t in source_rows(work, cfg["files"][n[0]]) if num == n[1]), "")
            names = [x for x in STRING_RE.findall(row.split("(", 1)[1] if "(" in row else "") if x in labels]
            side.setdefault(i, set()).update(names)
    return dict((u, v) for u, v in out.items() if v), dict((u, sorted(v)) for u, v in side.items() if v)


def norm_cond(cond):
    return re.sub(r"\s+", "", cond or "")


def guard_owner(cfg, fn, line, cond):
    """The if/while statement above FILE:LINE whose edge conditions include `cond`: an `elif` clause, which has no
    statement of its own at its line. None when there is none."""
    if "_guards" not in cfg:
        guards = {}
        for i, n in enumerate(cfg["nodes"]):
            if len(n) > 5:
                conds = set(norm_cond(c) for g in n[5] for c, _want in g)
                guards.setdefault(cfg["files"][n[0]], []).append((n[1], i, conds))
        cfg["_guards"] = guards
    want = norm_cond(cond)
    found = [(ln, i) for ln, i, conds in cfg["_guards"].get(fn, ()) if ln < line and want in conds]
    return max(found)[1] if found else None


def statement_nodes(cfg, ref, work=None):
    """Graph nodes of the statement at FILE:LINE. An `elif` line belongs to its `if` statement; any other line
    without a statement falls back to the nearest statement above it."""
    fn, line = parse_ref(ref)
    in_file = [(n[1], i) for i, n in enumerate(cfg["nodes"]) if cfg["files"][n[0]] == fn and n[1] <= line]
    if not in_file:
        die("no statement at or above %s in %s" % (ref, CFG))
    at_line = max(in_file)[0]
    if at_line != line and work:
        text = next((t for num, t in source_rows(work, fn) if num == line), "")
        m = re.match(r"\s*elif\s+(.+?)\s*:\s*$", text)
        owner = guard_owner(cfg, fn, line, m.group(1)) if m else None
        if owner is not None:
            return [owner]
    return [i for n, i in in_file if n == at_line]


def flow_range(work, d, cfg, var, gain, ref, start, via=None):
    """Print the range of the variable just before FILE:LINE along the story graph from `start` (only paths through
    the statement `via`, when given), split by the tracked flags when they matter; False if unreachable."""
    targets = set(statement_nodes(cfg, ref, work))
    through = set(statement_nodes(cfg, via, work)) if via else set()
    if "start" not in cfg["labels"]:
        print("# no `start` label in the story graph")
        return False
    g = story_graph(work, d, cfg)
    for limit in (MAX_FLAGS, MAX_FLAGS // 2, 2, 1, 0):
        try:
            result = flow_values(g, var, gain, targets, through, start, limit)
            break
        except TooManyStates:
            print("# more than %d path states per statement with up to %d flags; trying fewer" % (
                STATES_PER_STATEMENT, limit))
    if result == "via":
        print("# %s is not reachable from `start` in the story graph" % via)
        return False
    if result == "target":
        print("# %s is not reachable from %s in the story graph (a screen action or computed jump leads there)" % (
            ref, via or "`start`"))
        return False
    flags, per_val, repeat, loop, unknown = result
    if flags.names:
        # Flags unroll a loop once per combination of their values, so its gains can count several times; without
        # flags each counts once. Both are bounds under the same rule, so keep the tighter side of each.
        plain = flow_values(g, var, gain, targets, through, start, 0)
        p_hi, p_lo = max(v[0] for v in plain[1].values()), min(v[1] for v in plain[1].values())
        per_val = dict((val, [min(hi, p_hi), max(lo, p_lo)]) for val, (hi, lo) in per_val.items())
    lo, hi = min(v[1] for v in per_val.values()), max(v[0] for v in per_val.values())
    print("# before %s, along story paths from `start`%s: %g to %g (start %g)%s" % (
        ref, " through %s" % via if via else "", lo, hi, start,
        "; following %s" % ", ".join(flags.names) if flags.names else ""))
    for line in flag_breakdown(flags, per_val):
        print("#   " + line)
    print("# conditions on other variables count both ways")
    if repeat:
        print("# can repeat (a loop that comes back with the same flags): %s; the maximum counts each once" % ", ".join(
            "%s:%d" % (cfg["files"][cfg["nodes"][u][0]], cfg["nodes"][u][1]) for u in sorted(repeat)[:6]))
    elif loop >= BIG_LOOP:
        print("# the threshold sits inside a loop of %d statements, so the maximum counts every gain in that loop once"
              % loop)
    for u in sorted(set(unknown))[:5]:
        print("# not summed (not a constant change): %s" % u)
    return True


def flow_values(g, var, gain, targets, through, start, limit):
    """(flags, {flag values at the threshold: [max, min]}, repeatable gain nodes, loop size, unsummed changes), or
    the unreachable reference as a string. Raises TooManyStates when the flags multiply paths too much."""
    cfg = g.cfg
    flags, per_val, repeat, loop = None, {}, set(), 0
    for sign in (1, -1):
        effects, unknown = var_effects(g.d, var, gain, sign)
        at = dict((u, fn) for key, fn in effects.items() for u in g.at.get(key, ()) if g.nodes[u][2] == "p")
        if flags is None:
            flags = query_flags(g, set(at) | targets | through, var, limit)
        flow = StoryFlow(cfg, at, g.jumps, g.side, flags)
        state_in, adj, loops = flow.solve([flow.state(cfg["labels"]["start"])], enter_calls=True)
        arrivals = [(IDENTITY, state_in, adj, loops)]
        if through:
            starts = [(st, f) for st, f in state_in.items() if st[0] in through]
            if not starts:
                return "via"
            arrivals = [(f,) + flow.solve([st], enter_calls=True) for st, f in starts]
            if not any(at_nodes(a[1], targets) for a in arrivals):
                arrivals += back_to_callers(cfg, flow, arrivals, g.return_targets())
        found = {}
        for prefix, s_in, s_adj, s_loops in arrivals:
            for val, f in at_nodes(s_in, targets).items():
                found[val] = join(found.get(val, UNREACHED), then(prefix, f))
            loop = max([loop] + [size for st, size in s_loops.items() if st[0] in targets])
            if sign == 1:
                repeat |= repeatable_gains(s_adj, s_loops, at, targets)
        if not found:
            return "target"
        for val, f in found.items():
            per_val.setdefault(val, [None, None])[sign == -1] = sign * apply_fn(f, sign * start) + 0.0  # no "-0"
    return flags, per_val, repeat, loop, unknown


def back_to_callers(cfg, flow, arrivals, ret_to):
    """Continue paths that end at a called label's return (a `--via` statement inside the label) from the statements
    its callers continue with."""
    conts = {}
    for prefix, s_in, s_adj, _loops in arrivals:
        for (u, val), f in s_in.items():
            if cfg["nodes"][u][2] == "r" and not s_adj[(u, val)]:
                for v in ret_to.get(u, ()):
                    st = flow.state(v, val)
                    conts[st] = join(conts.get(st, UNREACHED), then(prefix, f))
    return [(f,) + flow.solve([st], enter_calls=True) for st, f in conts.items()]


def repeatable_gains(adj, loops, effects, targets):
    """Gain statements inside a loop of states (same flags each time round) from which the target is reachable."""
    radj = {}
    for u, outs in adj.items():
        for v, _fn in outs:
            radj.setdefault(v, []).append(u)
    seen, stack = set(), [st for st in adj if st[0] in targets]
    while stack:
        st = stack.pop()
        if st not in seen:
            seen.add(st)
            stack.extend(radj.get(st, ()))
    return set(st[0] for st in loops if st in seen and effects.get(st[0], IDENTITY)[0] > 0)


def flag_breakdown(flags, per_val, limit=6):
    """Lines like `escort=True: 4 to 6` when the range depends on tracked flag values."""
    groups = {}
    for val, (hi, lo) in per_val.items():
        groups.setdefault((lo, hi), []).append(val)
    if len(groups) < 2 or not flags.names:
        return []
    described = {}
    for rng, vals in groups.items():
        fixed = {}
        for i, name in enumerate(flags.names):
            values = set(repr(v[i]) for v in vals)
            if len(values) == 1 and vals[0][i] is not UNKNOWN:
                fixed[name] = values.pop()
        described[rng] = fixed
    shared = set.intersection(*[set(f.items()) for f in described.values()])
    out = []
    for rng in sorted(groups)[:limit]:
        label = ", ".join("%s=%s" % kv for kv in sorted(set(described[rng].items()) - shared)) or "other paths"
        out.append("%s: %g to %g" % (label, rng[0], rng[1]))
    if len(groups) > limit:
        out.append("... %d more combinations" % (len(groups) - limit))
    return out


def natural_key(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def cmd_list(args):
    d = load_dump(resolve_work(args.work_dir))
    load_replay_keys(resolve_work(args.work_dir))
    if args.group:
        groups = {}
        for m in d["menus"]:
            if args.file and not fnmatch.fnmatch(m["file"], args.file):
                continue
            effects = tuple(tuple(sorted("%s%s" % (v, op) for o in i["outline"] if o[2] == "python"
                                         for v, op, _ in assigned_vars(o[3]))) for i in m["items"])
            groups.setdefault((tuple(i["caption"] for i in m["items"]), effects), []).append(menu_id(m))
        for (caps, _effects), ids in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[1][0])):
            print("%3d x  %s\n       %s" % (len(ids), " | ".join(c[:40] for c in caps), " ".join(ids)))
        return
    print("#key\tlabel\tindex\tkind\tcondition\tcaption\tdialogue lines\tflags")
    for m in d["menus"]:
        if args.file and not fnmatch.fnmatch(m["file"], args.file):
            continue
        if args.label and m["label"] != args.label and nearest_label(d, m) != args.label:
            continue
        for i in m["items"]:
            print("\t".join([menu_id(m), m["label"] or "", str(i["index"]), "choice" if i["choice"] else "caption",
                             " ".join(x for x in ("" if i["condition"] == "True" else i["condition"], i.get("arguments", "")) if x),
                             i["caption"].replace("\n", "\\n"),
                             "say=%d" % i["say"], ",".join(f for f, on in (("replay-only", replay_only(m)), ("single-option", single_option(m)), ("menuset", bool(m.get("set")))) if on)]))
    work = resolve_work(args.work_dir)
    labels = {l["name"]: l for l in d["labels"]}
    for name, ls in sorted(list_sets(d, load_list_screens(work)).items()):
        site = ls["sites"][0]
        if args.file and not fnmatch.fnmatch(site["file"], args.file):
            continue
        for i in ls["items"] or []:
            target = labels.get(i["label"] or "")
            print("\t".join(["@" + name, ls["screen"], str(i["index"]), "choice",
                             "" if i["condition"] == "True" else str(i["condition"]), str(i["caption"]),
                             "-> %s (say=%d)" % (i["label"], target["say"]) if target else "-> %s" % i["label"]]))


def assigned_vars(code):
    out = []
    for line in code.split("\n"):
        m = ASSIGN_RE.match(line)
        if m:
            out.append((m.group(1), (m.group(2) or "") + "=", m.group(3).strip()))
    return out


def reads_of(d, var, skip):
    base = var.split("[")[0]
    pat = re.compile(r"(?<![\w.])%s\b" % re.escape(base))
    rv = []
    for r in d["reads"]:
        if (r["file"], r["line"]) in skip or not pat.search(r["code"]):
            continue
        if r["kind"] == "python":
            lines = [l for l in r["code"].split("\n") if pat.search(l)]
            if all(ASSIGN_RE.match(l) and pat.match(l.strip()) and not pat.search(ASSIGN_RE.match(l).group(3)) for l in lines):
                continue
        rv.append(r)
    return rv


def label_block(work, label):
    """Numbered source rows of a label's body: until a line at the label's indent or less (fall-through
    into a following label is followed), or a jump/return at body level."""
    view = source_view(work, label["file"], label["line"], label["line"] + 2000) or []
    rows = [r for r in view if len(r) > 9 and r[8] == "|"]  # "%7s | text" rows; skips the pseudo banner
    if not rows:
        return []
    head = rows[0].split("|", 1)[1]
    indent = len(head) - len(head.lstrip())
    out = [rows[0]]
    for r in rows[1:]:
        body = r.split("|", 1)[1]
        if not body.strip():
            continue
        ind = len(body) - len(body.lstrip())
        if ind <= indent and not body.lstrip().startswith("label "):
            break
        out.append(r)
        if ind == indent + 4 and re.match(r"\s*(jump|return)\b", body):
            break
    return out


def label_effects(work, d, label):
    """Effects inside a list item's target label: assignments, calls, jumps, gallery flags."""
    flags = gallery_flags(work)
    out = []
    for r in label_block(work, label):
        num, body = r.split("|", 1)
        code = body.strip()
        if code.startswith("$ ") or re.match(r"(call|jump|return)\b", code) or ASSIGN_RE.match(code):
            mark = ""
            m = re.match(r"\$?\s*([\w.]+)\s*[-+*/]?=(?!=)", code)
            if m and (m.group(1) in flags or m.group(1).split(".")[-1] in flags):
                mark = "   <== GALLERY unlock"
            out.append("<== L%s %s%s" % (num.strip() or "?", code[:110], mark))
    return out


def show_list(work, d, args):
    name = args.menu[1:]
    ls = list_sets(d, load_list_screens(work)).get(name)
    if ls is None:
        die("no call of a LIST_SCREENS screen with list %r" % name)
    labels = {l["name"]: l for l in d["labels"]}
    print("list @%s  screen=%s  defined at %s" % (name, ls["screen"], "%s:%d" % (ls["define"]["file"], ls["define"]["line"]) if ls["define"] else "?"))
    for c in ls["sites"]:
        print("  called at %s:%d  %s" % (c["file"], c["line"], c["code"]))
    for i in ls["items"] or []:
        cond = "" if i["condition"] == "True" else "  [if %s]" % i["condition"]
        target = labels.get(i["label"] or "")
        print("\n  [%d] %s%s   -> %s" % (i["index"], i["caption"], cond, "%s at %s:%d (say=%d)" % (i["label"], target["file"], target["line"], target["say"]) if target else i["label"]))
        if target:
            for row in label_effects(work, d, target):
                print("      " + row)
        if target and args.source:
            for row in source_view(work, target["file"], target["line"], target["line"] + args.source) or []:
                print("      " + row)
    rs = reads_of(d, name, set())
    if rs:
        print("\n  reads of %r:" % name)
        for r in rs[:args.reads]:
            print("    %s:%d %-7s %s" % (r["file"], r["line"], r["kind"], r["code"].strip().replace("\n", "; ")[:120]))


def cmd_show(args):
    work = resolve_work(args.work_dir)
    d = load_dump(work)
    if args.menu.startswith("@"):
        return show_list(work, d, args)
    m = find_menu(d, args.menu)
    load_replay_keys(work)
    labels = {l["name"]: l for l in d["labels"]}
    gallery = gallery_labels(work, d)
    SHOW_CTX.update(flags=gallery_flags(work), menu=m, brief=args.brief)
    near = nearest_label(d, m)
    print("menu %s  label=%s%s%s" % (menu_id(m), m["label"], "  (nearest label above: %s)" % near if near != m["label"] else "",
                                    "  (replay-only: hints never show)" if replay_only(m) else ""))
    if m.get("set"):
        print("  menuset %s: items already picked disappear, so the player picks several (a \"pick N of these\" hub)" % m["set"])
    if near in gallery:
        print("  inside gallery scene %s (L%d): hints show in normal play, the scene also replays from the gallery" % (near, labels[near]["line"]))
    for line, tag in m["chain"]:
        print("  inside L%d %s" % (line, tag))
    effects = {}
    for i in m["items"]:
        cond = "" if i["condition"] == "True" else "  [if %s]" % i["condition"]
        if i.get("arguments"):
            cond += "  [item arguments %s]" % i["arguments"]
        if not i["choice"]:
            print("\n  caption: %s" % i["caption"])
            continue
        print("\n  [%d] %s%s   (say=%d, nodes=%d, L%d)" % (i["index"], i["caption"], cond, i["say"], i["nodes"], i["line"]))
        print_outline(i, m, labels, gallery, effects)
    after = m.get("after")
    if after and after["outline"]:
        print("\n  after the menu (runs for every choice; flags set above often branch here)   (say=%d)" % after["say"])
        print_outline(after, m, labels, gallery, effects)
    print_reads(d, m, effects, args)
    print_source(work, m, args)


SHOW_CTX = {}


def print_outline(i, m, labels, gallery, effects):
    """Print an outline (a menu item or the after-menu block), marking assignments, gallery scenes and jumps."""
    stack = []
    for depth, line, kind, desc in i["outline"]:
        del stack[depth:]
        mark = ""
        where = [k for k in stack if k in ("menu", "if", "while")]
        nested = " (inside nested %s)" % "/".join(where) if where else ""
        if kind == "python":
            for var, op, val in assigned_vars(desc):
                effects.setdefault(var, set()).add((m["file"], line))
                mark = "   <== %s %s %s%s" % (var, op, val, nested)
            for flag, val in re.findall(r"persistent\.(\w+)\s*=\s*([^\n;]+)", desc):
                if flag in SHOW_CTX.get("flags", ()) and val.strip() in ("True", "1"):
                    mark += "   <== GALLERY unlock (persistent.%s)" % flag
        if kind in ("jump", "call", "label") and desc in labels:
            l = labels[desc]
            mark = "   -> %s:%d (say=%d)" % (l["file"], l["line"], l["say"])
            if kind == "jump" and l["file"] == m["file"] and l["line"] <= m["line"]:
                mark += "   (loops back above the menu)"
        if kind in ("jump", "call", "label") and desc in gallery:
            mark += "   <== GALLERY scene"
        if not SHOW_CTX.get("brief") or mark or kind in ("menu", "if", "call", "jump", "return"):
            print("      %s L%d %-6s %s%s" % ("  " * depth, line, kind, desc[:140].replace("\n", "; "), mark))
        stack.append(kind)
    if i.get("cut"):
        print("      ... %d more nodes not shown (outline limit); use --source" % i["cut"])


def print_reads(d, m, effects, args):
    if effects:
        print("\n  reads of assigned variables (if/while/menu conditions and python, excluding these assignments):")
        for var in sorted(effects):
            rs = reads_of(d, var, effects[var])
            rs.sort(key=lambda r: (natural_key(r["file"]), r["line"]))
            per_file = {}
            for r in rs:
                per_file[r["file"]] = per_file.get(r["file"], 0) + 1
            print("    %s: %d reads (%s)" % (var, len(rs), ", ".join("%s x%d" % kv for kv in sorted(per_file.items()))))
            for r in rs[:args.reads]:
                kind = r["kind"]
                if kind == "python" and all(COPY_RE.match(l) for l in r["code"].split("\n") if re.search(r"\b%s\b" % re.escape(var), l)):
                    kind = "copy"
                print("      %s:%d %-7s %s" % (r["file"], r["line"], kind, r["code"].strip().replace("\n", "; ")[:120]))
            if len(rs) > args.reads:
                print("      ... %d more (--reads N)" % (len(rs) - args.reads))


def print_source(work, m, args):
    if args.source:
        view = source_view(work, m["file"], m["line"] - 3, m["line"] + args.source)
        if view is None:
            print("\n  (no source; run `rpw.py extract`, or re-run `dump` for pseudo-source)")
            return
        print("\n  source %s:%d-%d" % (m["file"], m["line"], m["line"] + args.source))
        for row in view:
            print("  " + row)


# ---------------------------------------------------------------- gen / check

def duplicate_keys(path):
    """String keys that appear twice in one dict literal of a hints file (Python keeps only the last)."""
    tree = ast.parse(read_text(path), path)
    dups = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            seen = set()
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    if k.value in seen:
                        dups.append(k.value)
                    seen.add(k.value)
    return dups


def run_hints_file(path):
    try:
        return runpy.run_path(path)
    except Exception as e:  # a broken fragment must name itself, not crash every parallel agent
        die("%s: %s: %s" % (path, type(e).__name__, e))


def merged_setting(work, name):
    """A dict setting (SCREEN_NOTES, FLOW_EDGES) from hints.py and every hints.d/*.py fragment; a key set in two
    files is an error naming both."""
    p = os.path.join(work, "hints.py")
    out, origin = {}, {}
    for path in [p] + sorted(glob.glob(os.path.join(work, "hints.d", "*.py"))):
        if not os.path.exists(path):
            continue
        for key, value in run_hints_file(path).get(name, {}).items():
            if key in out:
                die("%s: %s key %s already set in %s" % (path, name, key, origin[key]))
            out[key], origin[key] = value, os.path.relpath(path, work)
            ORIGIN.setdefault(key, origin[key])
    return out


def load_hints(work):
    """SCOPE, HINTS, INPUT_HINTS, ANY from DIR/hints.py, with HINTS/INPUT_HINTS of DIR/hints.d/*.py merged in.
    ORIGIN maps every key to the file that defines it."""
    p = os.path.join(work, "hints.py")
    if not os.path.exists(p):
        die("%s missing; write it first (see reference/hints-format.md)" % p)
    files = [p] + sorted(glob.glob(os.path.join(work, "hints.d", "*.py")))
    for path in files:
        try:
            dups = duplicate_keys(path)
        except SyntaxError as e:
            die("%s: %s" % (path, e))
        if dups:
            die("%s: keys defined twice (only the last one counts): %s" % (path, sorted(set(dups))[:8]))
    ns = run_hints_file(p)
    hints, inputs = {}, {}
    for path in files:
        frag = ns if path == p else run_hints_file(path)
        if path != p:
            ignored = [k for k in ("SCOPE", "ANY", "LIST_SCREENS", "PATCH_DEFINES", "HINT_MAX_LEN") if k in frag]
            if ignored:
                sys.stderr.write("warning: %s defines %s; only hints.py's are used\n" % (path, ", ".join(ignored)))
        for name, src, dst in (("HINTS", frag.get("HINTS", {}), hints), ("INPUT_HINTS", frag.get("INPUT_HINTS", {}), inputs)):
            dup = set(src) & set(dst)
            if dup:
                die("%s: %s keys already defined in %s: %s" % (path, name, ORIGIN[sorted(dup)[0]], sorted(dup)[:5]))
            for k in src:
                ORIGIN[k] = os.path.relpath(path, work)
            dst.update(src)
    return ns.get("SCOPE", []), hints, inputs, ns.get("ANY", DEFAULT_ANY)


def normalize_spec(ref, spec, any_note, errors):
    """(note, items) for a hint value, None for SKIP; errors name the file the key came from."""
    if isinstance(spec, str) and spec.upper() in ("ANY", "SKIP"):
        return None if spec.upper() == "SKIP" else (any_note, {})
    if not (isinstance(spec, tuple) and len(spec) == 2 and isinstance(spec[1], dict)):
        errors.append("%s (%s): value must be \"ANY\", \"SKIP\" or (note, {index: (kind, text)}), got %r"
                      % (ref, ORIGIN.get(ref, "?"), spec))
        return None
    note, items = spec
    return (any_note if note == "ANY" else note), items


def parse_ref(ref):
    fn, _, line = ref.rpartition(":")
    if not fn or not line.isdigit():
        die("bad key %r: expected 'file.rpy:LINE'" % ref)
    return fn, int(line)


def hint_shape_ok(ref, idx, hint, errors):
    """True for an item hint `index: (kind, text)` with a non-negative int index and string text."""
    where = "%s[%r] (%s)" % (ref, idx, ORIGIN.get(ref, "?"))
    if not isinstance(idx, int) or isinstance(idx, bool) or idx < 0:
        errors.append("%s: the item index must be a whole number from 0" % where)
    elif not isinstance(hint, tuple) or len(hint) != 2:
        errors.append("%s: hint must be (kind, text)" % where)
    elif not isinstance(hint[1], str):
        errors.append("%s: hint text must be a string, got %r" % (where, hint[1]))
    else:
        return True
    return False


def build_table(work):
    """Return (menu table, input table, errors) from hints.py + dump."""
    d = load_dump(work)
    _, hints, input_hints, any_note = load_hints(work)
    menus = {(m["file"], m["line"]): m for m in d["menus"]}
    inputs = {(i["file"], i["line"]): i for i in d["inputs"]}
    table, itable, errors = {}, {}, []
    lists = list_sets(d, load_list_screens(work))
    for ref, spec in hints.items():
        if ref.startswith("@"):
            build_list_entry(ref, spec, lists, any_note, table, errors)
            continue
        fn_, _, line_ = ref.strip().rpartition(":")
        if ref != ref.strip() or not fn_ or not line_.isdigit():
            errors.append("%r (%s): key must be 'file.rpy:LINE' with no spaces" % (ref, ORIGIN.get(ref, "?")))
            continue
        key = (fn_, int(line_))
        m = menus.get(key)
        if m is None:
            errors.append("%s (%s): no menu statement at that line" % (ref, ORIGIN.get(ref, "?")))
            continue
        spec = normalize_spec(ref, spec, any_note, errors)
        if spec is None:
            continue
        note, items = spec
        if note is not None and not isinstance(note, str):
            errors.append("%s (%s): the note must be a string or None, got %r" % (ref, ORIGIN.get(ref, "?"), note))
            note = None
        entry = {"sig": m["items"][0]["caption"] if m["items"] else None, "note": note, "items": {}}
        for idx, hint in sorted(items.items(), key=lambda kv: repr(kv[0])):
            if not hint_shape_ok(ref, idx, hint, errors):
                continue
            kind, text = hint
            if idx >= len(m["items"]) or not m["items"][idx]["choice"]:
                errors.append("%s[%r] (%s): no choice item with that index" % (ref, idx, ORIGIN.get(ref, "?")))
                continue
            if kind not in KINDS:
                errors.append("%s[%d] (%s): kind %r is not one of %s" % (ref, idx, ORIGIN.get(ref, "?"), kind, KINDS))
            entry["items"][idx] = (m["items"][idx]["caption"], kind, text)
            entry.setdefault("conds", {})[idx] = m["items"][idx]["condition"]
        table[key] = entry
    for ref, text in input_hints.items():
        key = parse_ref(ref)
        i = inputs.get(key)
        if i is None:
            errors.append("input %s: no renpy.input statement at that line" % ref)
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append("input %s: the hint must be a non-empty string" % ref)
            continue
        itable[key] = (i["code"], text)
    return table, itable, errors


def build_screen_notes(work):
    """SCREEN_NOTES from hints.py -> ({(file, line): (statement source, note)}, errors). Keys are `call screen` sites."""
    notes = merged_setting(work, "SCREEN_NOTES")
    sites = {(c["file"], c["line"]): c["code"] for c in load_dump(work)["callscreens"]}
    table, errors = {}, []
    for ref, note in notes.items():
        key = parse_ref(ref)
        if key not in sites:
            errors.append("screen note %s: no `call screen` / renpy.call_screen statement at that line" % ref)
            continue
        if not isinstance(note, str) or not note.strip():
            errors.append("screen note %s: the note must be a non-empty string" % ref)
            continue
        table[key] = (sites[key], note)
    return table, errors


def build_list_entry(ref, spec, lists, any_note, table, errors):
    ls = lists.get(ref[1:])
    if ls is None:
        errors.append("%s (%s): no literal list of that name passed to a LIST_SCREENS screen" % (ref, ORIGIN.get(ref, "?")))
        return
    spec = normalize_spec(ref, spec, any_note, errors)
    if spec is None:
        return
    if not ls["items"]:
        errors.append("%s (%s): no literal list of that name passed to a LIST_SCREENS screen" % (ref, ORIGIN.get(ref, "?")))
        return
    note, items = spec
    entry = {"sig": ls["items"][0]["caption"], "note": note, "items": {}, "attr": ls["attr"]}
    for idx, hint in sorted(items.items()):
        if idx >= len(ls["items"]) or not isinstance(hint, tuple) or len(hint) != 2 or hint[0] not in KINDS:
            errors.append("%s[%r]: bad index or hint" % (ref, idx))
            continue
        entry["items"][idx] = (ls["items"][idx]["caption"], hint[0], hint[1])
        entry.setdefault("conds", {})[idx] = ls["items"][idx]["condition"]
    table[("@list", ref[1:])] = entry


def render_table(table, itable, stable=None):
    out = ["# WT-DATA-BEGIN", "define wt_hints = {"]
    for key in sorted(table):
        e = table[key]
        attr = ", \"attr\": %r" % e["attr"] if "attr" in e else ""
        out.append("    %r: {\"sig\": %r, \"note\": %r%s, \"items\": {" % (key, e["sig"], e["note"], attr))
        for idx in sorted(e["items"]):
            out.append("        %d: %r," % (idx, e["items"][idx]))
        out.append("    }},")
    out += ["}", "# WT-DATA-END", "",
            "## Typed prompts: (file, line of the `renpy.input` statement): (statement source, hint).",
            "# WT-INPUT-BEGIN", "define wt_input_hints = {"]
    for key in sorted(itable):
        out.append("    %r: %r," % (key, itable[key]))
    out += ["}", "# WT-INPUT-END", "",
            "## Notes over choices made with the game's own screens: (file, line of the `call screen`): (source, note).",
            "# WT-SCREEN-BEGIN", "define wt_screen_notes = {"]
    for key in sorted(stable or {}):
        out.append("    %r: %r," % (key, stable[key]))
    out += ["}", "# WT-SCREEN-END"]
    return "\n".join(out)


LIST_WRAPPER = """
screen wt_list_%(name)s(*args, **kwargs):
    $ wt_a, wt_k, wt_n = wt_list_args("%(name)s", args, kwargs)
    use wt_orig_%(name)s(*wt_a, **wt_k)
    use wt_overlay(wt_n)
"""


def cmd_gen(args):
    work = resolve_work(args.work_dir)
    d = load_dump(work)
    table, itable, errors = build_table(work)
    stable, serrors = build_screen_notes(work)
    errors += serrors
    if errors:
        for e in errors:
            print("error: " + e)
        sys.exit(1)
    tmpl = read_text(os.path.join(ASSETS, "walkthrough.rpy.tmpl"))
    tune_path = os.path.join(work, TUNE)
    tuned = os.path.exists(tune_path)
    list_screens = load_list_screens(work)
    out = (tmpl.replace("@TITLE@", d["name"] or "Game").replace("@HINTS@", render_table(table, itable, stable))
           .replace("@TUNED@", "True" if tuned else "False").replace("@LISTS@", repr(list_screens)))
    for name in sorted(list_screens):
        out += LIST_WRAPPER % {"name": name}
    for name, value in runpy.run_path(os.path.join(work, "hints.py")).get("PATCH_DEFINES", {}).items():
        out, n = re.subn(r"(?m)^define %s = .*$" % re.escape(name), "define %s = %r" % (name, value), out)
        if not n:
            die("PATCH_DEFINES: the template has no `define %s`" % name)
    if tuned:
        out += "\n## Tune mode: the game's choice screen, copied with room for the hint line (%s).\n\n" % TUNE
        out += read_text(tune_path)
    with open(os.path.join(work, PATCH), "w", encoding="utf-8") as f:
        f.write(out)
    print("wrote %s: %d menu entries, %d input entries, %d screen notes%s" % (
        os.path.join(work, PATCH), len(table), len(itable), len(stable), ", tuned choice screen" if tuned else ""))


def single_option(m):
    """A menu with exactly one choice item and no condition: a click-to-continue, nothing to hint."""
    choices = [i for i in m["items"] if i["choice"]]
    return len(choices) == 1 and choices[0]["condition"] == "True"


def changed_since_gen(work, d, gen_path, table, itable, stable):
    """Errors for hinted menus, input prompts and screen-note sites that are different in the current dump from
    when walkthrough.rpy was generated: after a game update another menu can sit at a hinted line."""
    old_table, old_inputs, old_screens = generated_tables(gen_path)
    menus = {(m["file"], m["line"]): m for m in d["menus"]}
    advice = "run `rpw.py migrate %s`, or re-analyse it and then run gen" % work
    errors = []
    for key in table:
        old = old_table.get(key)
        if old and key in menus and not find_moved(old, [menus[key]], key[0]):
            errors.append("%s:%d: this menu changed since walkthrough.rpy was generated (its first choice was %r); %s"
                          % (key[0], key[1], old["sig"], advice))
    for label, now, before in (("input", itable, old_inputs), ("screen note", stable, old_screens)):
        for key, (src, _text) in now.items():
            if key in before and before[key][0] != src:
                errors.append("%s %s:%d: this statement changed since walkthrough.rpy was generated (was %r); %s"
                              % (label, key[0], key[1], before[key][0][:60], advice))
    return errors


def other_menu_screen(m):
    """The screen a menu statement's own arguments send it to when that is not `choice` (menu (screen="phone"):,
    menu (nvl=True):), else None."""
    args = m.get("arguments") or ""
    screen = re.search(r"""\bscreen\s*=\s*u?['"]([\w.]+)['"]""", args)
    if screen and screen.group(1) != "choice":
        return "screen %r" % screen.group(1)
    if re.search(r"\bnvl\s*=\s*True\b", args):
        return "the NVL screen"
    return None


def error_in_scope(error, wanted, key_file):
    """For `check --only`: whether an error message (\"[input |screen note ]FILE:LINE ...\" or \"@list ...\")
    belongs to a file in scope. Errors that name no file are always kept."""
    m = re.match(r"(?:input |screen note )?'?(@[\w.]+|[^\s:'\[]+\.rpy)", error)
    if not m:
        return True
    ref = m.group(1)
    return wanted(key_file(("@list", ref[1:])) if ref.startswith("@") else ref)


def cmd_check(args):
    work = resolve_work(args.work_dir)
    d = load_dump(work)
    scope, hints, _, any_note = load_hints(work)
    load_replay_keys(work)
    table, itable, errors = build_table(work)
    stable, serrors = build_screen_notes(work)
    errors += serrors
    only = args.only.split(",") if args.only else None
    hint_max = runpy.run_path(os.path.join(work, "hints.py")).get("HINT_MAX_LEN", HINT_MAX_LEN)

    def wanted(fn):
        return any(fnmatch.fnmatch(fn, g) for g in scope) and (only is None or any(fnmatch.fnmatch(fn, g) for g in only))

    def key_file(key):
        if key[0] == "@list":
            ls = list_sets(d, load_list_screens(work)).get(key[1])
            return ls["sites"][0]["file"] if ls else ""
        return key[0]

    if only is not None:
        table = {k: v for k, v in table.items() if wanted(key_file(k))}
        itable = {k: v for k, v in itable.items() if wanted(k[0])}
        stable = {k: v for k, v in stable.items() if wanted(k[0])}
        errors = [e for e in errors if error_in_scope(e, wanted, key_file)]
    warnings = []
    for key, e in table.items():
        texts = [("note", e["note"])] + [("[%d]" % i, h[2]) for i, h in e["items"].items()]
        for where, text in texts:
            if not text:
                continue
            if where == "note" and len(text) > NOTE_MAX_LEN:
                warnings.append("%s:%s note: %d chars (max %d)" % (key[0], key[1], len(text), NOTE_MAX_LEN))
            if where != "note" and len(text) > hint_max:
                warnings.append("%s:%s %s: hint is %d chars (max %d)" % (key[0], key[1], where, len(text), hint_max))
            if "\u2014" in text or "\u2013" in text:
                errors.append("%s:%s %s: contains an em or en dash" % (key[0], key[1], where))
        if not e["note"] and not e["items"] and not any(e_.startswith("%s:%s" % key) for e_ in errors):
            warnings.append("%s:%s: entry has neither a note nor item hints" % key)
    for label, tab in (("input", itable), ("screen note", stable)):
        for key, (_src, text) in tab.items():
            if len(text) > NOTE_MAX_LEN:
                warnings.append("%s %s:%d: %d chars (max %d)" % (label, key[0], key[1], len(text), NOTE_MAX_LEN))
            if "\u2014" in text or "\u2013" in text:
                errors.append("%s %s:%d: contains an em or en dash" % (label, key[0], key[1]))
    gen_path = os.path.join(work, PATCH)
    if os.path.exists(gen_path):
        errors += changed_since_gen(work, d, gen_path, table, itable, stable)
    if only is None:
        warnings += unused_claims(work, d, table)
    if os.path.exists(gen_path) and only is None:
        if render_table(table, itable, stable) not in read_text(gen_path):
            warnings.append("%s is stale; re-run `rpw.py gen`" % gen_path)
    skipped = {parse_ref(r) for r, v in hints.items() if isinstance(v, str) and v.upper() == "SKIP" and not r.startswith("@")}
    skipped |= {("@list", r[1:]) for r, v in hints.items() if r.startswith("@") and isinstance(v, str) and v.upper() == "SKIP"}
    in_scope = [m for m in d["menus"] if wanted(m["file"])]
    for m in in_scope:
        e = table.get((m["file"], m["line"]))
        choices = [i["index"] for i in m["items"] if i["choice"]]
        if e and len(choices) == 2:
            kinds = {i: e["items"].get(i, (None, None, ""))[1] for i in choices}
            texts = {i: e["items"].get(i, (None, None, ""))[2] for i in choices}
            for a, b in (choices, choices[::-1]):
                # Point hints ("Rachel +1 (gallery scene at 4)") are not a scene the other choice skips.
                if kinds[a] == "good" and kinds[b] is None and SCENE_RE.search(texts[a]) and not POINTS_RE.search(texts[a]):
                    warnings.append("%s: [%d] is a scene payoff but [%d] has no hint; the rubric marks the alternative "
                                    "(bad \"Skips the scene\"), or info if it has its own payoff" % (menu_id(m), a, b))
    nvl_all = any(x["name"] == "menu" and "nvl_menu" in x["code"] for x in d.get("defines", []))
    if nvl_all:
        warnings.append("the game defines `menu = nvl_menu`: menus use the NVL screen, which the patch does not "
                        "wrap, so item hints won't show (use notes or a written walkthrough)")
    for m in in_scope:
        other = other_menu_screen(m)
        if other and table.get((m["file"], m["line"]), {}).get("items") and not nvl_all:
            warnings.append("%s: the menu is shown with %s, not `choice`; its item hints won't show in game"
                            % (menu_id(m), other))
    for m in in_scope:
        if replay_only(m) and (m["file"], m["line"]) in table:
            warnings.append("%s: hinted, but it only runs in replays (hints never show there)" % menu_id(m))
        elif single_option(m) and table.get((m["file"], m["line"]), {}).get("items"):
            warnings.append("%s: item hint on a single-option menu (the player has no choice)" % menu_id(m))
    uncovered = [m for m in in_scope if (m["file"], m["line"]) not in table and (m["file"], m["line"]) not in skipped]
    replay = [m for m in uncovered if replay_only(m)]
    single = [m for m in uncovered if not replay_only(m) and single_option(m)]
    gaps = [m for m in uncovered if not replay_only(m) and not single_option(m)]
    for m in gaps:
        print("gap: %s  %r" % (menu_id(m), m["items"][0]["caption"][:60] if m["items"] else ""))
    for name, ls in sorted(list_sets(d, load_list_screens(work)).items()):
        if any(wanted(c["file"]) for c in ls["sites"]) and ("@list", name) not in table and ("@list", name) not in skipped:
            gaps.append(name)
            print("gap: @%s  %r" % (name, (ls["items"] or [{}])[0].get("caption", "")))
    for w in warnings:
        print("warning: " + w)
    for e in errors:
        print("error: " + e)
    hinted = sum(1 for e in table.values() if e["items"])
    noted = sum(1 for e in table.values() if not e["items"] and e["note"] and e["note"] != any_note)
    print("%s%d entries (%d with item hints, %d note-only, %d ANY), %d input entries, %d screen notes, %d SKIP, auto-skipped: %d replay-only + %d single-option; %d errors, %d gaps, %d warnings" % (
        "[--only %s] " % args.only if only else "", len(table), hinted, noted, len(table) - hinted - noted, len(itable), len(stable),
        len([k for k in skipped if only is None or wanted(key_file(k))]), len(replay), len(single), len(errors), len(gaps), len(warnings)))
    if errors or gaps:
        sys.exit(1)


# ---------------------------------------------------------------- verify / install

def finding_lines(report_text):
    """Lint findings (lines naming a game file), ignoring the timestamp header and statistics."""
    return {l.strip() for l in report_text.split("\n") if l.startswith("game/")}


def lint_with(work, game, patch_text, label):
    gd = game["game_dir"]
    with open(os.path.join(gd, PATCH), "w", encoding="utf-8") as f:
        f.write(patch_text)
    report = os.path.join(work, "lint-%s.txt" % label)
    traceback = os.path.join(game["base"], "traceback.txt")
    had = os.path.getmtime(traceback) if os.path.exists(traceback) else None
    code, log = run_lint(game, report)
    if os.path.exists(traceback) and os.path.getmtime(traceback) != had:
        # Errors outside the lint pass itself (e.g. preparing screens) only land in traceback.txt.
        log += "\nTraceback written to %s:\n%s" % (traceback, read_text(traceback, errors="replace")[-3000:])
        if had is None:
            os.remove(traceback)
    write_text(os.path.join(work, "lint-%s-stdout.txt" % label), log)
    checks = [SELFCHECK_RE.match(l) for l in log.split("\n")]
    checks = [c for c in checks if c]
    details = [l for l in log.split("\n") if l.startswith("walkthrough: ") and not SELFCHECK_RE.match(l)]
    rtext = read_text(report, "utf-8-sig", "replace") if os.path.exists(report) else ""
    return code, log, checks, details, rtext


def cmd_verify(args):
    work = resolve_work(args.work_dir)
    game = load_game(work)
    gen_path = os.path.join(work, PATCH)
    if not os.path.exists(gen_path):
        die("%s missing; run `rpw.py gen %s`" % (gen_path, work))
    patch = read_text(gen_path)
    gd = game["game_dir"]
    clean_leftovers(game)
    installed = os.path.join(gd, PATCH)
    previous = read_text(installed) if os.path.exists(installed) else None
    baseline = read_text(os.path.join(work, "lint-baseline.txt"), "utf-8-sig", "replace")
    ok = True
    try:
        code, log, checks, details, rtext = lint_with(work, game, patch, "patched")
        if not checks:
            print("FAIL: no self-check line in lint output (patch did not load?)")
            print(log[-3000:])
            ok = False
        else:
            c = checks[-1]
            print("self-check: %s" % c.group(0))
            for line in details:
                print("  " + line)
            if int(c.group(2)) != 0:
                ok = False
        new = sorted(finding_lines(rtext) - finding_lines(baseline))
        print("lint: %d new findings vs baseline" % len(new))
        for l in new[:40]:
            print("  + " + l)
        if new or "Traceback" in log:
            ok = False
        if args.negative and ok:
            ok = negative_test(work, game, patch) and crash_test_init(work, game, patch)
        if ok and not args.no_render:
            ok = render_checks(work, game, patch, args.negative)
    finally:
        # Leave game/ as it was: the previously installed patch (even if this one failed), or nothing.
        remove_compiled(gd, PATCH)
        if args.keep:
            write_text(installed, patch)
        elif previous is not None:
            write_text(installed, previous)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def render_pick(table):
    """The menu that best exercises the patch: has item hints, then the longest hinted caption + hint."""
    def score(key):
        e = table[key]
        shown = [i for i in e["items"] if e.get("conds", {}).get(i, "True") in ("True", None)]
        longest = max([len(e["items"][i][0]) + len(e["items"][i][2]) for i in shown] or [0])
        return (bool(shown), bool(e["note"]), longest)
    if not table:
        return None
    best = max(table, key=score)
    return "@" + best[1] if best[0] == "@list" else "%s:%d" % best


CRASH = 'raise Exception("rpw crash test")'
CRASH_COPY = "# @RPW-CRASH-TEST-COPY@"  # only in verify's crash-test copy, never in a real patch


def crash_test_init(work, game, patch):
    """Inject a failure into the screen take-over: the game must still start, with the patch switched off."""
    if "# @RPW-CRASH-TEST-INIT@" not in patch:
        print("crash test: patch has no crash-test marker (generated by an older template?)")
        return False
    _, log, _, _, _ = lint_with(work, game, patch.replace("# @RPW-CRASH-TEST-INIT@", CRASH + "  " + CRASH_COPY),
                                "crash")
    good = "Traceback" not in log and "walkthrough: disabled after an error in screen take-over" in log
    print("crash test (init): %s" % ("game runs, patch disabled" if good else "FAILED\n" + log[-2000:]))
    return good


def clickable(probe_path):
    """(clickable rectangles, rectangles cut by the screen edge) from a probe file, or None if there is none.
    Ren'Py clips focus rectangles to the screen, so an item pushed fully off screen is simply missing."""
    if not os.path.exists(probe_path):
        return None
    p = json.loads(read_text(probe_path))
    w, h = p["width"], p["height"]
    edge = [r for r in p["rects"] if r[1] <= 0 or r[1] + r[3] >= h]  # vertical overflow is what hint lines cause
    return p["rects"], edge


FIT_MENUS = 3


def render_checks(work, game, patch, negative):
    """One game launch: render the most demanding hinted menu; for the tallest hinted menus compare hints on vs
    off (choices pushed off screen fail, wrapped hint lines warn); with `negative` prove a runtime error leaves the
    menu working without hints; render one screen note."""
    table = build_table(work)[0]
    pick = render_pick(table)
    if pick is None:
        return True
    fits = fit_picks(work, table)
    shots = [make_shot(work, pick)]
    pairs = []
    for n, ref in enumerate(fits):
        on = make_shot(work, ref, probe=True, label="fit%d-on" % n)
        off = make_shot(work, ref, "persistent.wt_enabled = False", probe=True, label="fit%d-off" % n)
        shots += [on, off]
        pairs.append((ref, on, off))
    if negative:
        shots.append(make_shot(work, pick, "wt_state.crash_test = True", label="crash"))
    notes = build_screen_notes(work)[0]
    note_shot = None
    if notes:
        note_shot = make_shot(work, "%s:%d" % sorted(notes)[0], "wt_state.failed = None\nwt_state.crash_test = False", label="note")
        shots.append(note_shot)
    log, finished = render_shots(work, game, shots, patch_text=patch)
    ok = True
    print("render: %s -> %s" % (pick, shots[0]["out"] if os.path.exists(shots[0]["out"]) else "FAILED"))
    if not os.path.exists(shots[0]["out"]) or not finished:
        print(log[-3000:])
        return False
    line = hint_line_height(work)
    for ref, on_shot, off_shot in pairs:
        ok = fit_report(ref, on_shot, off_shot, line) and ok
    if note_shot:
        good = os.path.exists(note_shot["out"])
        print("screen note: %s -> %s" % (note_shot["label"], note_shot["out"] if good else "FAILED"))
        ok = ok and good
    if negative:
        crash = [x for x in shots if x["label"].endswith("(crash)")][0]
        good = os.path.exists(crash["out"]) and "disabled after an error in wt_" in log
        print("crash test (runtime): %s" % ("menu still shows, patch disabled" if good else "FAILED\n" + log[-2000:]))
        ok = ok and good
    return ok


def hint_line_height(work):
    """Approximate height of one hint line in screen units, from the game's choice text size."""
    d = load_dump(work)
    size = define_value(d, "gui.choice_button_text_size") or define_value(d, "gui.text_size")
    return (size - 6) * 1.2 if isinstance(size, (int, float)) else None


def fit_report(ref, on_shot, off_shot, line):
    """Print the fit verdict for one menu. Choices lost off screen fail; wrapped hint lines only warn."""
    on, off = clickable(on_shot["probe"]), clickable(off_shot["probe"])
    if on is None or off is None:
        print("fit: %s -> no probe written" % ref)
        return False
    if len(on[0]) < len(off[0]) or len(on[1]) > len(off[1]):
        print("fit: %s -> with hints %d clickable item(s) disappear and %d touch the screen edge (without: %d). "
              "Shorten its hints, or set PATCH_DEFINES = {\"wt_long_menu_shift\": 1.0, \"wt_long_menu_from\": 1} in hints.py; see %s"
              % (ref, len(off[0]) - len(on[0]), len(on[1]), len(off[1]), on_shot["out"]))
        return False
    wrapped = wrapped_items(on[0], off[0], line)
    if wrapped:
        print("fit: %s -> fits, but %d button(s) grew by more than one hint line: a wrapped hint (shorten it or "
              "lower HINT_MAX_LEN) or, in tune mode, a long caption the game's fixed button used to cut off; look at %s"
              % (ref, wrapped, on_shot["out"]))
    else:
        print("fit: %s -> every item stays on screen, hints on one line (%d clickable)" % (ref, len(on[0])))
    return True


def wrapped_items(on_rects, off_rects, line):
    """How many buttons grew by clearly more than one hint line: their hint (or caption) wrapped."""
    key = lambda r: (round(r[0]), round(r[1]))
    on_sorted, off_sorted = sorted(on_rects, key=key), sorted(off_rects, key=key)
    growth = [a[3] - b[3] for a, b in zip(on_sorted, off_sorted) if a[3] - b[3] > 2]
    if not growth:
        return 0
    one_line = min([min(growth)] + ([line] if line else []))
    return sum(1 for g in growth if g > 1.6 * one_line)


def fit_picks(work, table, n=FIT_MENUS):
    """Hinted menus most likely to break the layout: the tallest ones (most unconditional choices), plus the one
    with the longest caption + hint (most likely to wrap)."""
    d = load_dump(work)
    # Items without a condition are the ones a preview reliably shows (others depend on story state).
    sizes = {(m["file"], m["line"]): (len([i for i in m["items"] if i["choice"] and i["condition"] == "True"]),
                                      len(m["items"])) for m in d["menus"]}
    for name, ls in list_sets(d, load_list_screens(work)).items():
        items = ls["items"] or []
        sizes[("@list", name)] = (len([i for i in items if i["condition"] == "True"]), len(items))
    hinted = [k for k, e in table.items() if e["items"]]
    tall = sorted(hinted, key=lambda k: (sizes.get(k, (0, 0)), len(table[k]["items"])), reverse=True)[:n]
    longest = max(hinted, key=lambda k: max(len(c) + len(t) for c, _, t in table[k]["items"].values()), default=None)
    picks = tall + ([longest] if longest is not None and longest not in tall else [])
    return ["@" + k[1] if k[0] == "@list" else "%s:%d" % k for k in picks]


def negative_test(work, game, patch):
    """Corrupt one hinted caption in a temporary copy and expect the self-check to name it."""
    table, itable, _ = build_table(work)
    target = next(((k, i) for k in sorted(table) for i in sorted(table[k]["items"])), None)
    if target is None:
        print("negative: no item hint to corrupt")
        return False
    key, idx = target
    caption, kind, text = table[key]["items"][idx]
    table[key]["items"][idx] = ("RPW-NEGATIVE " + caption, kind, text)
    stable = build_screen_notes(work)[0]
    corrupted = patch.replace(render_table(*build_table(work)[:2], stable=stable), render_table(table, itable, stable))
    _, _, checks, details, _ = lint_with(work, game, corrupted, "negative")
    named = any(("%r[%d]" % (key, idx)) in re.sub(r"\bu'", "'", l) for l in details)  # py2 engines print u'...'
    good = bool(checks) and int(checks[-1].group(2)) == 1 and named
    print("negative: corrupted %r[%d] -> %s" % (key, idx, "detected" if good else "NOT detected: %s" % details))
    return good


def make_shot(work, ref, setup=None, out=None, probe=False, label=None):
    """One preview shot: the menu at FILE:LINE (or a list screen call for @name), its PNG path and options."""
    if ref.startswith("@"):
        ls = list_sets(load_dump(work), load_list_screens(work)).get(ref[1:])
        if ls is None:
            die("no call of a LIST_SCREENS screen with list %r" % ref[1:])
        m = re.search(r"call screen\s+([\w.]+)\s*(?:\((.*)\))?\s*$", ls["sites"][0]["code"].strip())
        shot = {"call": "renpy.call_screen(%r%s)" % (m.group(1), ", " + m.group(2) if m and m.group(2) else "")}
        slug = "list-" + ref[1:]
    else:
        fn, line = parse_ref(ref)
        sites = {(c["file"], c["line"]) for c in load_dump(work)["callscreens"]}
        shot = {"goto": [fn, line]} if (fn, line) in sites else {"file": fn, "line": line}
        slug = "%s-%d" % (re.sub(r"\W+", "_", fn), line)
    if label:
        slug += "-" + label
    shot["out"] = os.path.abspath(out or os.path.join(work, "preview-%s.png" % slug))
    shot["setup"] = "\n".join(x for x in (input_defaults(work), setup) if x)
    shot["label"] = "%s%s" % (ref, " (%s)" % label if label else "")
    if probe:
        shot["probe"] = os.path.join(work, "probe-%s.json" % slug)
    return shot


def render_shots(work, game, shots, delay=2.0, patch_text=None):
    """Boot the game once with the patch and capture every shot. Returns (log, ok) where ok means the game
    reached the end of the batch; each shot's PNG/probe file exists only if it was captured."""
    if sum(1 for shot in shots if shot.get("goto")) > 1:
        die("a batch can hold only one `call screen` shot (it ends the run)")
    shots = sorted(shots, key=lambda shot: bool(shot.get("goto")))  # the jump to a statement ends the batch
    for shot in shots:
        for key in ("out", "probe"):
            if shot.get(key) and os.path.exists(shot[key]):
                os.remove(shot[key])
    gd = game["game_dir"]
    installed = os.path.join(gd, PATCH)
    previous = read_text(installed) if os.path.exists(installed) else None
    write_text(installed, patch_text if patch_text is not None else read_text(os.path.join(work, PATCH)))
    shutil.copy(os.path.join(ASSETS, PREVIEW), os.path.join(gd, PREVIEW))
    err_path = os.path.join(work, "preview-error.txt")
    if os.path.exists(err_path):
        os.remove(err_path)
    spec = {"shots": shots, "delay": delay, "err": err_path}
    traceback = os.path.join(game["base"], "traceback.txt")
    had_traceback = os.path.exists(traceback)
    started = time.time()
    log = ""
    out_path = os.path.join(work, "preview-stdout.txt")
    game_proc = None
    try:
        game_proc = launch_game(game, dict(ENGINE_ENV, RPW_PREVIEW=json.dumps(spec)), out_path)
        log = wait_for_preview(game_proc, (traceback, err_path), started)
        log = (read_text(out_path, errors="replace") if os.path.exists(out_path) else "") + log
    finally:
        if game_proc is not None and game_proc.poll() is None:  # interrupted: don't leave the game running
            game_proc.kill()
            game_proc.wait()
        remove_compiled(gd, PREVIEW)
        remove_compiled(gd, PATCH)
        if previous is not None:
            write_text(installed, previous)
    sys.stderr.write("preview run: %.0fs for %d shot(s)\n" % (time.time() - started, len(shots)))
    if os.path.exists(err_path):
        log += "\n--- game error ---\n%s" % read_text(err_path, errors="replace")[-3000:]
    if os.path.exists(traceback) and os.path.getmtime(traceback) >= started:
        log += "\n--- %s ---\n%s" % (traceback, read_text(traceback, errors="replace")[-3000:])
        if not had_traceback:
            os.remove(traceback)
    return log, "rpw-preview: done" in log


def render_menu(work, game, ref, setup=None, delay=2.0, out=None, patch_text=None):
    """Boot the game with the patch, show menu `ref`, save a screenshot. Return (png path or None, log)."""
    shot = make_shot(work, ref, setup, out)
    log, _ = render_shots(work, game, [shot], delay, patch_text)
    return (shot["out"] if os.path.exists(shot["out"]) else None), log


class GameProcess(object):
    """A running game window. On macOS .app bundles start through `open -g`, so the window never takes
    focus from the user's foreground app; elsewhere the launcher runs directly in its own session."""

    def __init__(self, game, env_extra, out_path):
        exe = game["lint"][0]
        self.exe = exe
        # The preview script writes the game's process id here, so kill() never has to guess.
        self.pid_path = out_path + ".pid"
        if os.path.exists(self.pid_path):
            os.remove(self.pid_path)
        env_extra = dict(env_extra, RPW_PIDFILE=self.pid_path)
        self.mac_app = sys.platform == "darwin" and "/Contents/MacOS/" in exe
        if self.mac_app:
            app = exe.split("/Contents/MacOS/")[0]
            envs = [x for k, v in sorted(env_extra.items()) for x in ("--env", "%s=%s" % (k, v))]
            self.proc = subprocess.Popen(["open", "-g", "-n", "-W"] + envs + ["--stdout", out_path, "--stderr", out_path, app],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            self.log = open(out_path, "w")
            self.proc = subprocess.Popen(game["lint"][:-1], env=engine_env(env_extra), stdout=self.log,
                                         stderr=subprocess.STDOUT, start_new_session=hasattr(os, "killpg"))

    def poll(self):
        return self.proc.poll()

    def game_pid(self):
        try:
            return int(read_text(self.pid_path).strip())
        except (OSError, ValueError):
            return None

    def kill(self):
        if self.mac_app:
            if self.proc.poll() is not None:
                return  # `open -W` returned: the game already quit, and any process found now is someone else's
            pid = self.game_pid()
            if pid is None:
                # Before the script wrote its pid: the newest process running this bundle's executable. Match the
                # bundle-relative path: macOS may run a quarantined app from a translocated copy elsewhere.
                tail = "/".join(self.exe.split("/")[-4:])
                found = subprocess.run(["pgrep", "-n", "-f", re.escape(tail)], capture_output=True,
                                       text=True).stdout.split()
                pid = int(found[0]) if found else None
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        elif hasattr(os, "killpg"):
            os.killpg(self.proc.pid, signal.SIGKILL)
        else:
            self.proc.kill()

    def wait(self, timeout=GAME_EXIT_TIMEOUT):
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()  # `open -W` waiting on a game we can't see; stop waiting rather than hang
            self.proc.wait()
        if not self.mac_app:
            self.log.close()
        if os.path.exists(self.pid_path):
            os.remove(self.pid_path)


def launch_game(game, env_extra, out_path):
    if os.path.exists(out_path):
        os.remove(out_path)
    return GameProcess(game, env_extra, out_path)


def wait_for_preview(proc, error_files, started):
    """Wait for the preview game to quit; kill it on timeout or as soon as it reports an error."""
    note = ""
    while proc.poll() is None:
        if time.time() - started > PREVIEW_TIMEOUT:
            note = "timed out after %ds (an error screen or a prompt is probably waiting)" % PREVIEW_TIMEOUT
            proc.kill()
            break
        if any(os.path.exists(p) and os.path.getmtime(p) >= started for p in error_files):
            time.sleep(1)
            proc.kill()
            break
        time.sleep(0.5)
    proc.wait()
    return note


def input_defaults(work):
    """Python that gives every typed-name variable its renpy.input default, so captions like [mcname] render in preview."""
    lines = []
    for i in load_dump(work)["inputs"]:
        m = re.match(r"\s*([\w.]+)\s*=\s*renpy\.input\((.*)\)", i["code"].split("\n")[0])
        if not m:
            continue
        try:
            call = ast.parse("f(%s)" % m.group(2), mode="eval").body
        except SyntaxError:
            continue
        default = next((k.value for k in call.keywords if k.arg == "default"), call.args[1] if len(call.args) > 1 else None)
        default = default.args[0] if isinstance(default, ast.Call) and default.args else default
        if isinstance(default, ast.Constant) and isinstance(default.value, str) and default.value:
            lines.append("try:\n    %s = %r\nexcept Exception:\n    pass" % (m.group(1), default.value))
    return "\n".join(lines)


def cmd_preview(args):
    """Boot the game with the patch, show one menu, save a screenshot, quit."""
    work = resolve_work(args.work_dir)
    game = load_game(work)
    if not os.path.exists(os.path.join(work, PATCH)):
        die("%s missing; run `rpw.py gen %s`" % (os.path.join(work, PATCH), work))
    png, log = render_menu(work, game, args.menu, args.setup, args.delay, args.out)
    if png is None:
        die("no screenshot; game output:\n%s" % log[-5000:])
    print("screenshot: %s" % png)


README = """# %(title)s walkthrough patch

Made with the `renpy-walkthrough` skill from the game's own code. Hints appear under the game's
choices:
- green ▲ = a gain
- red ▼ = a loss
- grey ● = neutral
- a note line at the top for menu-wide advice

Press **W** (or click "Walkthrough: on" in the corner of a menu) to toggle hints. They are hidden in gallery replays.

## Coverage

%(coverage)s

%(uncovered)s
## Notes

%(notes)s

## Commands

```sh
S=~/.claude/skills/renpy-walkthrough/rpw.py
python3 -I $S install %(slug)s      # copy walkthrough.rpy into the game
python3 -I $S uninstall %(slug)s    # remove walkthrough.rpy/.rpyc
python3 -I $S gen %(slug)s && python3 -I $S check %(slug)s && python3 -I $S verify %(slug)s --negative
```

**After a game update**
Run `python3 -I $S update %(slug)s`. It re-dumps the game, moves hints whose menus only moved, and stops
with a list of changed or new menus to re-analyse; when there are none it regenerates, verifies and installs.

Until you do, outdated entries stay hidden in game; they are not shown wrong.
"""


def cmd_readme(args):
    """Write DIR/README.md: coverage from the hints, what can't be hinted from recon, the commands."""
    work = resolve_work(args.work_dir)
    path = os.path.join(work, "README.md")
    if os.path.exists(path) and not args.force:
        die("%s exists; pass --force to rewrite it" % path)
    d = load_dump(work)
    load_replay_keys(work)
    table, itable, _ = build_table(work)
    hinted = sum(1 for e in table.values() if e["items"])
    noted = sum(1 for e in table.values() if not e["items"])
    replay = sum(1 for m in d["menus"] if replay_only(m))
    single = sum(1 for m in d["menus"] if not replay_only(m) and single_option(m))
    coverage = ["- %d menus/lists have hints under the choices." % hinted,
                "- %d have a note only (dialogue-only, cosmetic or menu-wide advice)." % noted]
    if replay or single:
        coverage.append("- %d replay-only and %d single-option menus need none." % (replay, single))
    if itable:
        coverage.append("- %d typed prompts have a hint." % len(itable))
    stable = build_screen_notes(work)[0]
    if stable:
        coverage.append("- %d choices made with the game's own screens show a note at the top (W toggles it too)." % len(stable))
    unc = []
    for site, names in button_choice_sets(work, d):
        noted = parse_ref(site) in stable
        unc.append("- `%s`: choice made of buttons (%s)%s" % (site, ", ".join(names), ": has a note" if noted else ""))
    for p_ in d["pymenus"]:
        unc.append("- `%s:%d`: menu shown from Python" % (p_["file"], p_["line"]))
    uncovered = ("## Not covered\n\nThese choices bypass the game's menu screen, so the patch can't hint them:\n\n%s\n\n" % "\n".join(unc[:30])) if unc else ""
    notes = getattr(args, "notes", None)
    if not notes and os.path.exists(path):
        m = re.search(r"\n## Notes\n\n(.*?)\n\n## Commands", read_text(path), re.S)
        notes = m.group(1) if m else None  # keep the hand-written notes when regenerating
    notes = notes or "(Main payoffs and anything the player should know.)"
    write_text(path, README % {"title": d["name"], "coverage": "\n".join(coverage), "uncovered": uncovered,
                               "notes": notes, "slug": os.path.basename(os.path.normpath(work))})
    print("wrote %s" % path)


def generated_tables(path):
    """(menu table, input table) as written into a generated walkthrough.rpy."""
    text = read_text(path)
    def block(begin, end):
        if begin not in text:
            return {}
        part = text[text.index(begin) + len(begin):text.index(end)]
        return ast.literal_eval(part[part.index("=") + 1:].strip())
    return (block("# WT-DATA-BEGIN", "# WT-DATA-END"), block("# WT-INPUT-BEGIN", "# WT-INPUT-END"),
            block("# WT-SCREEN-BEGIN", "# WT-SCREEN-END"))


def find_moved(old, menus, prefer_file):
    """Menus in the new dump whose first caption and hinted captions match an old table entry."""
    def matches(m):
        caps = [i["caption"] for i in m["items"]]
        return caps and caps[0] == old["sig"] and all(
            idx < len(caps) and caps[idx] == hint[0] for idx, hint in old["items"].items())
    same = [m for m in menus if m["file"] == prefer_file and matches(m)]
    return same if same else [m for m in menus if matches(m)]


def cmd_migrate(args):
    """After a game update: move hint keys to the menus' new lines when their captions still match uniquely."""
    work = resolve_work(args.work_dir)
    gen_path = os.path.join(work, PATCH)
    if not os.path.exists(gen_path):
        die("%s missing: migrate needs the walkthrough.rpy generated before the update (it holds the old captions)" % gen_path)
    old_table, old_inputs, old_screens = generated_tables(gen_path)
    d = load_dump(work)
    _, hints, input_hints, _ = load_hints(work)
    menus = d["menus"]
    current = {(m["file"], m["line"]): m for m in menus}
    moves, lost, unchanged = {}, [], 0
    for ref in hints:
        if ref.startswith("@"):
            continue
        key = parse_ref(ref)
        old = old_table.get(key)
        if old is None:
            continue  # SKIP entries and keys added after the last gen
        m = current.get(key)
        if m and find_moved(old, [m], key[0]):
            unchanged += 1
            continue
        found = find_moved(old, menus, key[0])
        if len(found) == 1:
            moves[ref] = menu_id(found[0])
        else:
            lost.append("%s (%s): %s" % (ref, ORIGIN.get(ref, "?"), "menu text changed or removed" if not found
                                         else "%d matching menus: %s" % (len(found), ", ".join(menu_id(x) for x in found[:5]))))
    inputs = {(i["file"], i["line"]): i for i in d["inputs"]}
    for ref in input_hints:
        key = parse_ref(ref)
        old = old_inputs.get(key)
        if old is None or (key in inputs and inputs[key]["code"] == old[0]):
            unchanged += old is not None
            continue
        found = [i for i in d["inputs"] if i["code"] == old[0]]
        if len(found) == 1:
            moves[ref] = "%s:%d" % (found[0]["file"], found[0]["line"])
        else:
            lost.append("input %s (%s): %s" % (ref, ORIGIN.get(ref, "?"), "prompt changed or removed" if not found else "ambiguous"))
    sites = {(c["file"], c["line"]): c["code"] for c in d["callscreens"]}
    screen_notes = merged_setting(work, "SCREEN_NOTES")
    for ref in screen_notes:
        key = parse_ref(ref)
        ORIGIN.setdefault(ref, "hints.py")
        old = old_screens.get(key)
        if old is None or sites.get(key) == old[0]:
            unchanged += old is not None
            continue
        found = [k for k, code in sites.items() if code == old[0]]
        if len(found) == 1:
            moves[ref] = "%s:%d" % found[0]
        else:
            lost.append("screen note %s: %s" % (ref, "call screen statement changed or removed" if not found else "ambiguous"))
    taken = set(hints) | set(input_hints) | set(screen_notes)
    clashes = [r for r, new in moves.items() if new in taken and new not in moves]
    for r in clashes:
        lost.append("%s -> %s: that key is already used by another entry" % (r, moves.pop(r)))
    targets = {}
    for r, new in moves.items():
        targets.setdefault(new, []).append(r)
    for new, refs in targets.items():
        if len(refs) > 1:  # copy-pasted menus where one was removed: which hint belongs where is unclear
            for r in refs:
                lost.append("%s -> %s: %d keys would move to the same menu" % (r, moves.pop(r), len(refs)))
    prev_path = os.path.join(work, "rpw_dump.prev.json")
    prev = json.loads(read_text(prev_path)) if os.path.exists(prev_path) else None
    if prev is None:
        print("note: no rpw_dump.prev.json, so \"not used yet\" hints can't be compared with the previous version")
    for line in stale_unused(d, prev, hints, moves):
        print("recheck " + line)
    for ref, new in sorted(moves.items()):
        print("move  %s -> %s   (%s)" % (ref, new, ORIGIN.get(ref, "?")))
    for line in lost:
        print("lost  " + line)
    recheck = stale_unused(d, prev, hints, moves)
    print("%d unchanged, %d moved, %d need a human" % (unchanged, len(moves), len(lost) + len(recheck)))
    if args.write and moves:
        rewrite_keys(work, moves)
        print("rewrote keys; next: rpw.py check, gen, verify")
    elif moves:
        print("dry run: pass --write to rewrite the keys")
    if lost or recheck:
        sys.exit(1)


UNUSED_RE = re.compile(r"not used yet|unused|gates nothing|never read", re.I)


def stale_unused(d, prev, hints, moves):
    """Hints that call a stat unused, where a variable that choice assigns gained a read with the update
    (a condition or Python read in the new dump that the previous dump didn't have)."""
    if prev is None:
        return []
    known = {(r["file"], r["kind"], r["code"].strip()) for r in prev["reads"]}
    menus = {(m["file"], m["line"]): m for m in d["menus"]}
    out = []
    for ref, spec in hints.items():
        if ref.startswith("@") or not isinstance(spec, tuple):
            continue
        key = parse_ref(moves.get(ref, ref))
        m = menus.get(key)
        if m is None:
            continue
        for idx, hint in spec[1].items():
            if not (isinstance(hint, tuple) and len(hint) == 2 and UNUSED_RE.search(hint[1])) or idx >= len(m["items"]):
                continue
            assigned = {var for o in m["items"][idx]["outline"] if o[2] == "python" for var, _op, _v in assigned_vars(o[3])}
            sites = {(m["file"], o[1]) for o in m["items"][idx]["outline"]}
            read = [(var, r) for var in sorted(assigned) for r in reads_of(d, var, sites)
                    if (r["kind"] != "python" or not COPY_RE.match(r["code"].strip()))
                    and (r["file"], r["kind"], r["code"].strip()) not in known]
            if read:
                var, r = read[0]
                out.append("%s[%d] says %r, but the update added a read of %s at %s:%d (%s)" % (
                    ref, idx, hint[1], var, r["file"], r["line"], r["code"].strip()[:60]))
    return out


def cmd_update(args):
    """After a game update: re-dump, re-key moved hints, report what needs new analysis, and if nothing does,
    regenerate, verify and reinstall."""
    work = resolve_work(args.work_dir)
    game = load_game(work)
    if not os.path.exists(os.path.join(work, PATCH)):
        die("%s missing: update needs the patch generated for the previous version" % os.path.join(work, PATCH))
    remove_compiled(game["game_dir"], PATCH)
    run_step("dump", [game["source"], "--work", work])  # keeps the old dump as rpw_dump.prev.json; re-extracts src/
    stop = ("\nupdate stopped: analyze the entries above (rpw.py show), fix hints.py, then run `rpw.py gen`, "
            "`check`, `verify --negative`, `install`. The patch is not installed.")
    if run_step("migrate", [work, "--write"], allow_fail=True) != 0 or run_step("check", [work], allow_fail=True) != 0:
        print(stop)
        sys.exit(1)
    run_step("gen", [work])
    run_step("verify", [work, "--negative"])
    run_step("install", [work])


def run_step(name, argv, allow_fail=False):
    print("\n== rpw.py %s %s" % (name, " ".join(argv)), flush=True)
    p = subprocess.run([sys.executable, "-I", os.path.abspath(__file__), name] + argv)
    if p.returncode != 0 and not allow_fail:
        die("`%s` failed; stopping" % name)
    return p.returncode


def rewrite_keys(work, moves):
    """Replace each moved key's string literal in the file that defines it (two passes, so chains can't collide).
    Every file is checked before any is written, and each one changed keeps a .bak copy."""
    by_file = {}
    for ref, new in moves.items():
        by_file.setdefault(ORIGIN[ref], []).append((ref, new))
    rewritten = {}
    for rel, pairs in by_file.items():
        text = read_text(os.path.join(work, rel))
        for n, (ref, _new) in enumerate(pairs):
            hits = len(re.findall(r"([\"'])%s\1" % re.escape(ref), text))
            if hits != 1:
                die("%s: key %r appears %d times; edit it by hand (no file was changed)" % (rel, ref, hits))
            text = re.sub(r"([\"'])%s\1" % re.escape(ref), r"\g<1>@RPW-MOVE-%d@\g<1>" % n, text)
        for n, (_ref, new) in enumerate(pairs):
            text = text.replace("@RPW-MOVE-%d@" % n, new)
        rewritten[rel] = text
    for rel, text in rewritten.items():
        path = os.path.join(work, rel)
        shutil.copy(path, path + ".bak")
        write_text(path, text)


SPOT_BRIEF = """# Blind spot-check: %(title)s

Re-derive walkthrough hints for the %(n)d menus below **from the game's code only**, so they can be
compared with the existing hints. Do not open `hints.py`, `hints.d/`, `walkthrough.rpy`, `README.md`,
`spotcheck/` (except to write your answer) or any `preview-*.png` in the work dir: the point is an
independent second opinion.

- Work dir: `%(work)s` (dump, `src/`, `pseudo/`). Helper: `python3 -I %(rpw)s <cmd>`.
- Read `%(skill)s/reference/rubric.md` and `hints-format.md` first and apply them.
- Per menu: `rpw.py show %(slug)s KEY --source 40`, `rpw.py budget %(slug)s VAR`, and the source.
- Write `%(work)s/spotcheck/blind.py` with `HINTS = {...}` for exactly these keys (same format as
  hints-format.md: `(note, {index: (kind, text)})` or `"ANY"`). Give every choice with a real payoff a
  hint; leave neutral items out. Add a one-line comment per key with the evidence (file:line).

Keys:
%(keys)s
"""


def spot_sample(table, n, seed):
    """A reproducible sample of table keys: about 70%% with item hints, the rest note-only or ANY."""
    import random
    rng = random.Random(seed)
    hinted = sorted((k for k, e in table.items() if e["items"]), key=str)
    plain = sorted((k for k, e in table.items() if not e["items"]), key=str)
    want_h = min(len(hinted), max(1, int(round(n * 0.7))))
    pick = rng.sample(hinted, want_h) + rng.sample(plain, min(len(plain), n - want_h))
    return sorted(pick, key=lambda k: (str(k[0]), str(k[1])))


def key_ref(key):
    return "@" + key[1] if key[0] == "@list" else "%s:%d" % key


def cmd_spotcheck(args):
    """Blind second opinion on a sample of hints: write a brief for a fresh agent, or compare its answer."""
    work = resolve_work(args.work_dir)
    out_dir = os.path.join(work, "spotcheck")
    table = build_table(work)[0]
    if args.compare:
        return spot_compare(work, table, out_dir)
    if args.sample < 1:
        die("--sample must be at least 1")
    os.makedirs(out_dir, exist_ok=True)
    seed = args.seed if args.seed is not None else int(hashlib.sha1(work.encode()).hexdigest()[:8], 16)
    keys = spot_sample(table, args.sample, seed)
    write_text(os.path.join(out_dir, "sample.json"), json.dumps([key_ref(k) for k in keys]))
    brief = SPOT_BRIEF % {"title": load_dump(work)["name"], "n": len(keys), "work": work,
                          "rpw": os.path.abspath(__file__), "skill": SKILL_DIR,
                          "slug": os.path.basename(work), "keys": "\n".join("- `%s`" % key_ref(k) for k in keys)}
    write_text(os.path.join(out_dir, "brief.md"), brief)
    print("wrote %s (%d keys, seed %d); give it to a fresh agent, then run `rpw.py spotcheck %s --compare`"
          % (os.path.join(out_dir, "brief.md"), len(keys), seed, os.path.basename(work)))


def spot_compare(work, table, out_dir):
    """Grade the blind hints against the real ones, per choice item."""
    sample_path = os.path.join(out_dir, "sample.json")
    if not os.path.exists(sample_path):
        die("%s missing: run `rpw.py spotcheck %s --sample N` first" % (sample_path, os.path.basename(work)))
    sample = json.loads(read_text(sample_path))
    blind_path = os.path.join(out_dir, "blind.py")
    if not os.path.exists(blind_path):
        die("%s missing: the blind agent hasn't answered yet" % blind_path)
    blind = run_hints_file(blind_path).get("HINTS", {})
    rows, counts = [], {"agree": 0, "minor": 0, "missed": 0, "overclaim": 0, "conflict": 0, "unanswered": 0}
    for ref in sample:
        if ref not in blind:  # nothing to grade: its real hints are not "overclaims"
            counts["unanswered"] += 1
            rows.append("unanswered %s" % ref)
            continue
        key = ("@list", ref[1:]) if ref.startswith("@") else parse_ref(ref)
        real = table.get(key, {"items": {}})["items"]
        spec = blind.get(ref)
        theirs = spec[1] if isinstance(spec, tuple) else {}
        for idx in sorted(set(real) | set(theirs)):
            a = real.get(idx)
            b = theirs.get(idx)
            ka, kb = (a[1] if a else None), (b[0] if isinstance(b, tuple) else None)
            if ka == kb:
                grade = "agree"
            elif {ka, kb} == {"good", "bad"}:
                grade = "conflict"
            elif ka in (None, "info") and kb in ("good", "bad"):
                grade = "missed"
            elif ka in ("good", "bad") and kb in (None, "info"):
                grade = "overclaim"
            else:
                grade = "minor"
            counts[grade] += 1
            if grade != "agree":
                rows.append("%-9s %s[%d]\n    ours:  %s\n    blind: %s" % (
                    grade, ref, idx, "%s %r" % (ka, a[2]) if a else "-", "%s %r" % (kb, b[1]) if kb else "-"))
    order = {"conflict": 0, "missed": 1, "overclaim": 2, "minor": 3, "unanswered": 4}
    rows.sort(key=lambda r: order.get(r.split()[0], 9))
    report = "\n".join(rows + ["", "%(agree)d agree, %(conflict)d conflict, %(missed)d missed, %(overclaim)d overclaim, "
                                    "%(minor)d minor, %(unanswered)d unanswered" % counts,
                                "Adjudicate conflicts and missed/overclaim items against the code; fix whichever side is wrong."])
    write_text(os.path.join(out_dir, "report.txt"), report)
    print(report)


def cmd_install(args):
    work = resolve_work(args.work_dir)
    game = load_game(work)
    src = os.path.join(work, PATCH)
    if not os.path.exists(src):
        die("%s missing; run `rpw.py gen %s`" % (src, work))
    remove_compiled(game["game_dir"], PATCH)
    shutil.copy(src, os.path.join(game["game_dir"], PATCH))
    print("installed %s" % os.path.join(game["game_dir"], PATCH))
    if sys.platform == "darwin" and ".app/" in game["game_dir"]:
        app = game["game_dir"].split(".app/")[0] + ".app"
        print("if macOS refuses to open the modified app: xattr -dr com.apple.quarantine %r" % app)


def cmd_uninstall(args):
    work = resolve_work(args.work_dir)
    game = load_game(work)
    clean_leftovers(game)
    remove_compiled(game["game_dir"], PATCH)
    print("removed %s(c)" % os.path.join(game["game_dir"], PATCH))


# ---------------------------------------------------------------- main

def on_signal(signum, _frame):
    """SIGTERM/SIGHUP (a tool timeout, a closed terminal) unwind like an error, so every `finally` that removes
    test files from game/ still runs."""
    raise SystemExit(128 + signum)


def main(argv):
    for name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), on_signal)
    ap = argparse.ArgumentParser(prog="rpw.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("locate", cmd_locate), ("dump", cmd_dump)):
        p = sub.add_parser(name); p.add_argument("target"); p.add_argument("--work")
        p.add_argument("--extract-to", help="where to unpack a .zip (default: next to the zip)"); p.set_defaults(fn=fn)
    p = sub.add_parser("check"); p.add_argument("work_dir")
    p.add_argument("--only", help="comma-separated globs: report gaps only in these files"); p.set_defaults(fn=cmd_check)
    for name, fn in (("extract", cmd_extract), ("recon", cmd_recon), ("gen", cmd_gen),
                     ("install", cmd_install), ("uninstall", cmd_uninstall)):
        p = sub.add_parser(name); p.add_argument("work_dir"); p.set_defaults(fn=fn)
    p = sub.add_parser("list"); p.add_argument("work_dir"); p.add_argument("--file"); p.add_argument("--label")
    p.add_argument("--group", action="store_true", help="cluster menus with identical captions (copy-pasted menus)")
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("work_dir"); p.add_argument("menu")
    p.add_argument("--source", type=int, default=0, help="also print N source lines from DIR/src")
    p.add_argument("--reads", type=int, default=12, help="max read sites per variable")
    p.add_argument("--brief", action="store_true", help="only effects, jumps, gates and nested menus")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("preview"); p.add_argument("work_dir"); p.add_argument("menu")
    p.add_argument("--setup", help="python run in the store first, e.g. 'PhoneChoice = True'")
    p.add_argument("--delay", type=float, default=2.0); p.add_argument("--out"); p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("migrate"); p.add_argument("work_dir")
    p.add_argument("--write", action="store_true", help="rewrite the keys (default: dry run)"); p.set_defaults(fn=cmd_migrate)
    p = sub.add_parser("spotcheck"); p.add_argument("work_dir")
    p.add_argument("--sample", type=int, default=12); p.add_argument("--seed", type=int)
    p.add_argument("--compare", action="store_true", help="grade spotcheck/blind.py against the real hints")
    p.set_defaults(fn=cmd_spotcheck)
    p = sub.add_parser("update"); p.add_argument("work_dir"); p.set_defaults(fn=cmd_update)
    p = sub.add_parser("readme"); p.add_argument("work_dir"); p.add_argument("--force", action="store_true")
    p.add_argument("--notes", help="text for the Notes section"); p.set_defaults(fn=cmd_readme)
    p = sub.add_parser("budget"); p.add_argument("work_dir")
    p.add_argument("--before", help="FILE:LINE of a threshold: the range reachable just before it, along story paths")
    p.add_argument("--via", help="FILE:LINE of a statement inside a choice (e.g. its `+= 2`): only paths through it, "
                                 "to see whether that choice decides the threshold; used with --before")
    p.add_argument("--gain", help="regex whose group 1 is an amount added, for method-based systems "
                                  "(e.g. 'Noelle\\.pointch\\((-?\\d+)'); used with --before")
    p.add_argument("var", help="a variable name, or a regex for method-based systems (e.g. 'Miya\\.(points|pointch)')")
    p.set_defaults(fn=cmd_budget)
    p = sub.add_parser("verify"); p.add_argument("work_dir"); p.add_argument("--negative", action="store_true")
    p.add_argument("--keep", action="store_true", help="leave the patch installed")
    p.add_argument("--no-render", action="store_true", help="skip booting the game to render one hinted menu")
    p.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv[1:])
    if args.cmd in ("verify", "preview", "install", "uninstall"):
        with game_lock(load_game(resolve_work(args.work_dir))):
            args.fn(args)
        return
    args.fn(args)


if __name__ == "__main__":
    main(sys.argv)
