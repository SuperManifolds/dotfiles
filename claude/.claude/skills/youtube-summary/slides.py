#!/usr/bin/env python3
"""Pick the frames of a video that are worth looking at, and save them.

Decodes only the keyframes of a local video file, as tiny thumbnails (a few
seconds per hour of video), decides which moments matter, and saves those
frames at full resolution.

A "shot" is a run of keyframes that stay close to the frame the run started
with: one slide, one camera angle, one animation scene. Small changes inside a
shot are bullet points building up, so each shot is represented by its last
settled keyframe, when the slide is complete. A whiteboard filling up slowly
drifts away from its starting frame and so becomes several shots. Shots that
look like an earlier one (a camera cutting back, a slide shown again) are
merged. Long stretches left without a frame get one if it shows something
new. If more frames remain than the cap allows, the video is split into equal
time buckets and the longest-shown shot wins each bucket.

Usage: slides.py <video file> <out dir> --max N [--debug]
Prints a JSON list of {index, seconds, shownSeconds, path} to stdout.
"""

import argparse
import concurrent.futures
import itertools
import json
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

THUMB_WIDTH, THUMB_HEIGHT = 64, 36
FULL_SCALE = 255

# A change counts as major when it exceeds both an absolute floor and a multiple
# of the video's typical keyframe-to-keyframe motion (its median difference).
MAJOR_CHANGE_FLOOR = 0.03
MAJOR_CHANGE_NOISE_FACTOR = 4.0
# Frames closer than this fraction of the major threshold show the same thing.
DUPLICATE_FRACTION = 0.5
# A keyframe is settled when it barely differs from the one before it.
SETTLED_FRACTION = 0.35
MIN_SHOT_KEYFRAMES = 2
# A returning camera angle or slide is nearly always a recent one.
REPEAT_LOOKBACK = 40
# No stretch longer than this multiple of (duration / cap) is left uncovered.
MAX_GAP_FACTOR = 1.5
GRAB_WORKERS = 6
GRAB_ATTEMPTS = 2
GRAB_TIMEOUT_SECONDS = 60


@dataclass
class Shot:
    seconds: float          # timestamp of the representative keyframe
    thumb: bytes
    shown_seconds: float    # total time this shot (and its repeats) is on screen


def read_keyframes(video: Path) -> tuple[list[float], list[bytes]]:
    """Decode only keyframes, as tiny grayscale thumbnails with their timestamps."""
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-nostats",
         "-skip_frame", "nokey", "-i", str(video), "-an", "-fps_mode", "passthrough",
         "-vf", f"scale={THUMB_WIDTH}:{THUMB_HEIGHT},format=gray,showinfo",
         "-f", "rawvideo", "-"],
        capture_output=True, check=False)
    if result.returncode != 0:
        tail = result.stderr.decode(errors="replace").strip().splitlines()[-2:]
        raise RuntimeError(f"ffmpeg could not decode {video}: {' '.join(tail)}")
    times = [float(value) for value in re.findall(rb"pts_time:\s*([0-9.]+)", result.stderr)]
    size = THUMB_WIDTH * THUMB_HEIGHT
    thumbs = [result.stdout[i:i + size] for i in range(0, len(result.stdout) - size + 1, size)]
    count = min(len(times), len(thumbs))
    pairs = sorted(zip(times[:count], thumbs[:count]), key=lambda pair: pair[0])
    return [t for t, _ in pairs], [thumb for _, thumb in pairs]


def difference(a: bytes, b: bytes) -> float:
    """Mean absolute pixel difference, 0 (identical) to 1."""
    return sum(abs(x - y) for x, y in zip(a, b)) / (len(a) * FULL_SCALE)


def find_shots(times: list[float], thumbs: list[bytes], duration: float) -> tuple[list[Shot], float, list[float]]:
    diffs = [difference(a, b) for a, b in itertools.pairwise(thumbs)]
    noise = statistics.median(diffs) if diffs else 0.0
    major = max(MAJOR_CHANGE_FLOOR, MAJOR_CHANGE_NOISE_FACTOR * noise)
    settled = major * SETTLED_FRACTION

    boundaries = [0]
    reference = thumbs[0]
    for i in range(1, len(thumbs)):
        if diffs[i - 1] >= major or difference(reference, thumbs[i]) >= major:
            boundaries.append(i)
            reference = thumbs[i]
    boundaries.append(len(times))

    shots = []
    for start, end in itertools.pairwise(boundaries):
        if end - start < MIN_SHOT_KEYFRAMES:
            continue
        # Latest keyframe that has stopped changing; the complete slide.
        pick = next((i for i in range(end - 1, start, -1) if diffs[i - 1] < settled), end - 1)
        shot_end = times[end] if end < len(times) else duration
        shots.append(Shot(times[pick], thumbs[pick], shot_end - times[start]))
    return shots, major, diffs


def merge_repeats(shots: list[Shot], major: float) -> list[Shot]:
    limit = major * DUPLICATE_FRACTION
    kept: list[Shot] = []
    for shot in shots:
        match = next((k for k in reversed(kept[-REPEAT_LOOKBACK:])
                      if difference(k.thumb, shot.thumb) < limit), None)
        if match is None:
            kept.append(shot)
        elif match is kept[-1]:
            # Same shot continuing after a blip: the later frame is the fuller one.
            kept[-1] = Shot(shot.seconds, shot.thumb, match.shown_seconds + shot.shown_seconds)
        else:
            match.shown_seconds += shot.shown_seconds
    return kept


def fill_gaps(shots: list[Shot], times: list[float], thumbs: list[bytes], diffs: list[float],
              duration: float, cap: int, major: float) -> list[Shot]:
    """Add a frame inside any long uncovered stretch, unless it shows nothing new."""
    max_gap = MAX_GAP_FACTOR * duration / cap
    limit = major * DUPLICATE_FRACTION
    filled: list[Shot] = []
    previous_time, previous = 0.0, None
    for shot in shots + [None]:
        gap_end = shot.seconds if shot else duration
        steps = int((gap_end - previous_time) / max_gap)
        for step in range(1, steps + 1):
            target = previous_time + (gap_end - previous_time) * step / (steps + 1)
            window = [i for i, t in enumerate(times) if abs(t - target) <= max_gap / 4 and i > 0]
            if not window:
                continue
            # The calmest keyframe near the target is the least likely to be mid-transition.
            pick = min(window, key=lambda i: diffs[i - 1])
            neighbours = [n for n in (filled[-1] if filled else previous, shot) if n]
            if any(difference(n.thumb, thumbs[pick]) < limit for n in neighbours):
                continue
            filled.append(Shot(times[pick], thumbs[pick], 0.0))
        if shot:
            filled.append(shot)
            previous_time, previous = shot.seconds, shot
    return filled


def limit_shots(shots: list[Shot], duration: float, cap: int) -> list[Shot]:
    if len(shots) <= cap:
        return shots
    bucket = duration / cap
    winners: dict[int, Shot] = {}
    for shot in shots:
        slot = min(cap - 1, int(shot.seconds / bucket))
        if slot not in winners or shot.shown_seconds > winners[slot].shown_seconds:
            winners[slot] = shot
    chosen = list(winners.values())
    spare = sorted((s for s in shots if all(s is not c for c in chosen)), key=lambda s: -s.shown_seconds)
    chosen += spare[:cap - len(chosen)]
    return sorted(chosen, key=lambda s: s.seconds)


def evenly_spaced(times: list[float], thumbs: list[bytes], duration: float, cap: int) -> list[Shot]:
    count = min(cap, len(times))
    step = len(times) / count
    picks = [int(step * (i + 0.5)) for i in range(count)]
    return [Shot(times[i], thumbs[i], duration / count) for i in picks]


def grab(source: Path, seconds: float, path: Path) -> bool:
    for _ in range(GRAB_ATTEMPTS):
        try:
            result = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-ss", f"{seconds:.2f}", "-i", str(source),
                 "-frames:v", "1", str(path)],
                capture_output=True, check=False, timeout=GRAB_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0 and path.exists() and path.stat().st_size > 0:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--max", type=int, required=True, dest="cap")
    parser.add_argument("--debug", action="store_true", help="report detection details on stderr")
    args = parser.parse_args()
    if args.cap < 1:
        parser.error("--max must be at least 1")

    try:
        times, thumbs = read_keyframes(args.video)
    except RuntimeError as error:
        print(f"slides: {error}", file=sys.stderr)
        return 1
    if not times:
        print("slides: no keyframes decoded", file=sys.stderr)
        return 1
    duration = times[-1] + (times[-1] - times[-2] if len(times) > 1 else 0)

    found, major, diffs = find_shots(times, thumbs, duration)
    merged = merge_repeats(found, major)
    if found:
        covered = fill_gaps(merged, times, thumbs, diffs, duration, args.cap, major)
        chosen = limit_shots(covered, duration, args.cap)
    else:
        # Nothing ever holds still (constant motion); fall back to even coverage.
        covered = chosen = evenly_spaced(times, thumbs, duration, args.cap)
    if args.debug:
        print(f"slides: keyframes={len(times)} major={major:.3f} shots={len(found)} "
              f"unique={len(merged)} with_fill={len(covered)} chosen={len(chosen)}", file=sys.stderr)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for stale in args.out_dir.glob("slide_*.png"):
        stale.unlink()
    targets = [(shot, args.out_dir / f"slide_{index:03d}_{int(shot.seconds)}s.png")
               for index, shot in enumerate(chosen, start=1)]
    with concurrent.futures.ThreadPoolExecutor(GRAB_WORKERS) as pool:
        results = list(pool.map(lambda target: grab(args.video, target[0].seconds, target[1]), targets))

    slides = [{"index": index, "seconds": int(shot.seconds),
               "shownSeconds": int(shot.shown_seconds), "path": str(path)}
              for index, ((shot, path), ok) in enumerate(zip(targets, results), start=1) if ok]
    failed = len(targets) - len(slides)
    if failed:
        print(f"slides: {failed} of {len(targets)} frames could not be grabbed", file=sys.stderr)
    json.dump(slides, sys.stdout, indent=1)
    print()
    return 0 if slides else 1


if __name__ == "__main__":
    sys.exit(main())
