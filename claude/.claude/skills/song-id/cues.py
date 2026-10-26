#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""List every music cue in a Ren'Py game with the dialogue that plays under it.

Usage: cues.py --music DIR --out CUES.json SCRIPT [more scripts ...]

SCRIPT is a plain `.rpy` file or a renpy-walkthrough `pseudo/*.rpy.txt` file
(`  <line> |  <code>`); pass them in story order. DIR holds the game's music
files (anything under it with an audio extension); a cue counts as music only
when it names one of them, which drops ambience and sound effects. Aliases from
`define audio.x = "..."`, playlists (`play music [a, b]`), `"<from 12>file"`
offsets and music fired on `sound` channels are all resolved.

Each cue records its script, line, scene label, channel (`music2`/`music3`
are layers over the main track), tracks, why the excerpt ends, speakers, the
last lines before it and up to --max-lines lines of dialogue under it. The
excerpt runs linearly, so it can cross into choice branches.
"""

import argparse
import json
import re
from pathlib import Path

AUDIO_EXTENSIONS = {".ogg", ".mp3", ".opus", ".wav", ".flac", ".m4a"}
LINES_BEFORE_SCANNED = 40
LINES_BEFORE_KEPT = 8
DEFAULT_MAX_LINES = 90
LABELS_PASSED_KEPT = 6
PLAYER = "MC"

PSEUDO_LINE = re.compile(r"^\s*(\d+)?\s*\|(.*)$")
LABEL = re.compile(r"^\s*label ([A-Za-z0-9_.]+)")
PLAY = re.compile(r"^\s*(?:stmt )?(play|queue) ((?:music|sound)\d?) (.+)$")
STOP = re.compile(r"^\s*(?:stmt )?stop ((?:music|sound)\d?)")
SAY = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)?\s*"(.*)"\s*(with .*)?$')
DEFINE_AUDIO = re.compile(r'define audio\.([A-Za-z0-9_]+) = "([^"]+)"')
CHARACTER = re.compile(r'define ([A-Za-z0-9_]+) = Character\(\s*(?:_\()?"([^"]*)"')
TEXT_TAG = re.compile(r"\{[^}]*\}")
CUE_OPTIONS = re.compile(r"\s(?:fadein|fadeout|volume|loop|noloop|if_changed)\b")
CUE_NAMES = re.compile(r'"(?:<[^>]*>)?([^"<]+)"|([A-Za-z_][A-Za-z0-9_]*)')


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def script_rows(path: Path) -> list[tuple[int | None, str]]:
    text = path.read_text(errors="replace").splitlines()
    if path.name.endswith(".rpy.txt"):
        return [(int(m.group(1)) if m.group(1) else None, m.group(2)) for raw in text if (m := PSEUDO_LINE.match(raw))]
    return [(number, raw) for number, raw in enumerate(text, start=1)]


def definitions(scripts: list[Path]) -> tuple[dict[str, str], dict[str, str]]:
    """Audio aliases and character names. Defines usually live in other files
    than the story, so every script in the same folders is read."""
    aliases, characters = {}, {}
    for path in {p for s in scripts for p in s.parent.iterdir() if p.is_file() and p.name.endswith((".rpy", ".rpy.txt"))}:
        for raw in path.read_text(errors="replace").splitlines():
            if m := DEFINE_AUDIO.search(raw):
                aliases[m.group(1)] = m.group(2)
            if m := CHARACTER.search(raw):
                name = TEXT_TAG.sub("", m.group(2)).strip()
                # A name that is only an interpolation ("[name]") is the player character.
                characters[m.group(1)] = PLAYER if re.fullmatch(r"\[[^\]]+\]", name) else name
    return aliases, characters


def resolve(argument: str, aliases: dict[str, str], music: dict[str, str]) -> tuple[list[str], str]:
    head = CUE_OPTIONS.split(argument)[0]
    tracks = []
    for quoted, ident in CUE_NAMES.findall(head):
        path = quoted or aliases.get(ident, ident)
        if track := music.get(squash(Path(path).stem)):
            tracks.append(track)
    return tracks, head.strip()


def cues_in(path: Path, aliases: dict[str, str], characters: dict[str, str], music: dict[str, str], max_lines: int) -> list[dict]:
    rows = script_rows(path)
    out, label = [], None
    for i, (number, body) in enumerate(rows):
        if m := LABEL.match(body):
            label = m.group(1)
            continue
        play = PLAY.match(body)
        if not play:
            continue
        channel = play.group(2)
        tracks, alias = resolve(play.group(3), aliases, music)
        if not tracks:
            continue
        before = [TEXT_TAG.sub("", s.group(2)) for _, b in rows[max(0, i - LINES_BEFORE_SCANNED) : i] if (s := SAY.match(b))]
        excerpt, speakers, labels_passed, ends = [], set(), [], "excerpt cap"
        for _, b in rows[i + 1 :]:
            if m := LABEL.match(b):
                labels_passed.append(m.group(1))
            if (p := PLAY.match(b)) and p.group(2) == channel:
                ends = "next cue on this channel"
                break
            if (s := STOP.match(b)) and s.group(1) == channel:
                ends = "music stopped"
                break
            if say := SAY.match(b):
                who = characters.get(say.group(1), say.group(1)) if say.group(1) else "Narration"
                speakers.add(who)
                excerpt.append(f"{who}: {TEXT_TAG.sub('', say.group(2))}")
                if len(excerpt) >= max_lines:
                    break
        out.append({
            "id": f"{path.name.split('.')[0]}:{number}", "script": path.name, "line": number, "label": label,
            "labels_passed": labels_passed[:LABELS_PASSED_KEPT], "channel": channel, "alias": alias, "tracks": tracks,
            "ends": ends, "speakers": sorted(speakers), "before": before[-LINES_BEFORE_KEPT:], "excerpt": excerpt,
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="List every music cue in Ren'Py scripts with the dialogue under it.")
    parser.add_argument("--music", type=Path, required=True, help="folder with the game's music files")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("scripts", nargs="+", type=Path)
    args = parser.parse_args()
    missing = [str(p) for p in [args.music, *args.scripts] if not p.exists()]
    if missing:
        parser.error(f"not found: {', '.join(missing)}")
    music = {squash(p.stem): p.stem for p in args.music.rglob("*") if p.suffix.lower() in AUDIO_EXTENSIONS}
    if not music:
        parser.error(f"no audio files under {args.music}")
    aliases, characters = definitions(args.scripts)
    cues = [cue for script in args.scripts for cue in cues_in(script, aliases, characters, music, args.max_lines)]
    args.out.write_text(json.dumps(cues, indent=1, ensure_ascii=False))
    used = {t for c in cues for t in c["tracks"]}
    print(f"{len(cues)} cues, {len(used)} of {len(music)} music files used -> {args.out}")
    for script in args.scripts:
        print(f"  {script.name}: {sum(c['script'] == script.name for c in cues)}")


main()
