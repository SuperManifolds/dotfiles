#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["shazamio"]
# ///
"""Identify audio files against Shazam and AudD.

Usage: identify.py [--no-audd] [--jsonl RESULTS] <audio file> [more files ...]

Cuts short mono WAV clips from each file with ffmpeg, matches every clip
against Shazam and one clip against AudD. The two catalogues disagree often enough on stock
music that both are worth printing, and a Shazam hit on a single clip is often
a coincidental match, so the verdict line reports how many clips agree and
whether the matched title resembles the filename.

--jsonl appends one record per file and skips files already recorded, so an
interrupted sweep resumes where it stopped. --no-audd keeps a sweep inside
AudD's small anonymous daily quota; AUDD_API_TOKEN lifts that quota.
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import aiohttp
from shazamio import Shazam
from shazamio.exceptions import FailedDecodeJson

CLIP_SECONDS = 15
CLIP_SAMPLE_RATE_HZ = 16000
CLIP_POSITIONS = (0.15, 0.45, 0.75)
AUDD_CLIP_INDEX = 1
AUDD_URL = "https://api.audd.io/"
AUDD_TIMEOUT_SECONDS = 60
SHAZAM_PAUSE_SECONDS = 1.0
MIN_TITLE_OVERLAP_CHARS = 4
MIN_AGREEING_CLIPS = 2
LOOKUP_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, FailedDecodeJson, subprocess.CalledProcessError, ValueError)


def duration_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def cut_clip(path: Path, offset: float, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-ss", f"{offset:.1f}", "-t", str(CLIP_SECONDS), "-i", str(path),
            "-ac", "1", "-ar", str(CLIP_SAMPLE_RATE_HZ), str(dest),
        ],
        check=True, capture_output=True, text=True,
    )


def squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def title_resembles_filename(title: str, path: Path) -> bool:
    a, b = squash(title), squash(path.stem)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= MIN_TITLE_OVERLAP_CHARS and (a in b or b in a))


async def shazam_match(shazam: Shazam, clip: Path) -> dict | None:
    track = (await shazam.recognize(str(clip))).get("track")
    if not track:
        return None
    meta = {m.get("title"): m.get("text") for s in track.get("sections", []) for m in s.get("metadata", [])}
    return {
        "id": track.get("key"),
        "artist": track.get("subtitle"),
        "title": track.get("title"),
        "url": track.get("url"),
        "album": meta.get("Album"),
        "label": meta.get("Label"),
        "isrc": track.get("isrc"),
        "orphan": not (track.get("isrc") or meta.get("Album")),
    }


async def audd_match(clip: Path) -> dict:
    form = aiohttp.FormData()
    form.add_field("file", clip.read_bytes(), filename=clip.name)
    form.add_field("return", "apple_music,spotify,deezer")
    if token := os.environ.get("AUDD_API_TOKEN"):
        form.add_field("api_token", token)
    timeout = aiohttp.ClientTimeout(total=AUDD_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session, session.post(AUDD_URL, data=form) as resp:
        body = await resp.json(content_type=None)
    result = body.get("result")
    if not result:
        return {"error": str(body["error"])} if body.get("error") else {}
    return {
        "artist": result.get("artist"),
        "title": result.get("title"),
        "album": result.get("album"),
        "label": result.get("label"),
        "released": result.get("release_date"),
        "link": result.get("song_link"),
        "spotify": ((result.get("spotify") or {}).get("external_urls") or {}).get("spotify"),
        "deezer": (result.get("deezer") or {}).get("link"),
    }


def describe_shazam(hit: dict | None) -> str:
    if hit is None:
        return "no match"
    detail = "ORPHAN RECORD (no ISRC/album)" if hit["orphan"] else f"album={hit['album']} label={hit['label']} isrc={hit['isrc']}"
    return f"{hit['artist']} - {hit['title']} | id={hit['id']} | {hit['url']} | {detail}"


def describe_audd(hit: dict) -> str:
    if "error" in hit:
        return f"error: {hit['error']}"
    if not hit:
        return "no match"
    return (
        f"{hit['artist']} - {hit['title']} | album={hit['album']} label={hit['label']} "
        f"released={hit['released']} | {hit['link']} | spotify={hit['spotify']} deezer={hit['deezer']}"
    )


def verdict(path: Path, hits: list[dict | None], audd: dict | None) -> dict:
    matched = [h for h in hits if h]
    if not matched:
        return {"shazam": None, "clips_agreeing": 0, "trust": "none"}
    top_id, count = Counter(h["id"] for h in matched).most_common(1)[0]
    best = next(h for h in matched if h["id"] == top_id)
    filename_match = title_resembles_filename(best["title"] or "", path)
    audd_agrees = bool(audd and audd.get("title") and squash(audd["title"]) == squash(best["title"] or ""))
    if audd_agrees or filename_match:
        trust = "confirmed"
    elif count < MIN_AGREEING_CLIPS:
        trust = "weak"
    elif best["orphan"]:
        trust = "renamed-release"
    else:
        trust = "consistent"
    return {"shazam": best, "clips_agreeing": count, "filename_match": filename_match, "audd_agrees": audd_agrees, "trust": trust}


async def identify(shazam: Shazam, path: Path, workdir: Path, use_audd: bool) -> dict:
    total = duration_seconds(path)
    print(f"{path} ({total:.0f}s, {int(total // 60)}:{int(total % 60):02d})")
    hits: list[dict | None] = []
    audd: dict | None = None
    for index, position in enumerate(CLIP_POSITIONS):
        offset = max(0.0, min(total * position, total - CLIP_SECONDS))
        clip = workdir / f"clip_{index}.wav"
        cut_clip(path, offset, clip)
        hit = await shazam_match(shazam, clip)
        hits.append(hit)
        print(f"  shazam @{offset:5.0f}s: {describe_shazam(hit)}")
        if use_audd and index == AUDD_CLIP_INDEX:
            audd = await audd_match(clip)
            print(f"  audd   @{offset:5.0f}s: {describe_audd(audd)}")
        await asyncio.sleep(SHAZAM_PAUSE_SECONDS)
    result = verdict(path, hits, audd)
    if result["shazam"]:
        print(
            f"  verdict: {result['trust']} | {result['clips_agreeing']}/{len(hits)} clips agree "
            f"| title~filename={result['filename_match']} | audd agrees={result['audd_agrees']}"
        )
    else:
        print("  verdict: none | shazam matched no clip")
    return {"file": str(path), "duration": round(total, 1), "audd": audd, **result}


def already_done(jsonl: Path | None) -> set[str]:
    if jsonl is None or not jsonl.exists():
        return set()
    return {json.loads(line)["file"] for line in jsonl.read_text().splitlines() if line.strip()}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Identify audio files against Shazam and AudD.")
    parser.add_argument("files", nargs="+", type=Path, metavar="audio-file")
    parser.add_argument("--no-audd", action="store_true", help="skip AudD (anonymous quota is a few requests per day)")
    parser.add_argument("--jsonl", type=Path, help="append one JSON record per file; files already recorded are skipped")
    args = parser.parse_args()

    missing = [str(p) for p in args.files if not p.is_file()]
    if missing:
        sys.exit(f"not a file: {', '.join(missing)}")
    done = already_done(args.jsonl)
    shazam = Shazam()
    with tempfile.TemporaryDirectory(prefix="song-id-") as tmp:
        for path in args.files:
            if str(path) in done:
                print(f"{path}: already in {args.jsonl}, skipped")
                continue
            try:
                record = await identify(shazam, path, Path(tmp), use_audd=not args.no_audd)
            except LOOKUP_ERRORS as error:
                detail = (getattr(error, "stderr", None) or str(error)).strip().splitlines()[-1]
                print(f"  error: {type(error).__name__}: {detail}")
                record = {"file": str(path), "error": f"{type(error).__name__}: {detail}"}
            if args.jsonl and "error" not in record:
                with args.jsonl.open("a") as out:
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")


asyncio.run(main())
