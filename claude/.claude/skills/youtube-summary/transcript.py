#!/usr/bin/env python3
"""Shape timed transcript segments into a readable, navigable transcript.

Writes the transcript as one paragraph per ~30 s under a `## [time] title`
heading per section, and prints the manifest lines that describe it: every
section with its line range and word count, and, for long videos, batches of
sections sized for one reader each.

Sections are the video's chapters; a video without chapters is cut into
fixed-length parts.

Usage: transcript.py <segments.json> <meta.json> <transcript.txt>
  segments.json: [{"startMs": int, "text": str}, ...]
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

PARAGRAPH_SECONDS = 30
PART_SECONDS = 15 * 60          # section length when the video has no chapters
MIN_CHAPTERS = 2                # a single chapter says nothing about structure
LONG_TRANSCRIPT_WORDS = 25_000  # above this, one reader should not take it all
BATCH_WORDS = 9_000             # target size of one reader's share
SMALL_BATCH_FRACTION = 1 / 3    # a final batch smaller than this joins the previous one


@dataclass
class Section:
    start: float
    title: str | None
    paragraphs: list[tuple[float, str]] = field(default_factory=list)
    first_line: int = 0
    last_line: int = 0

    @property
    def words(self) -> int:
        return sum(len(text.split()) for _, text in self.paragraphs)


def clock(seconds: float) -> str:
    whole = int(seconds)
    hours, minutes, secs = whole // 3600, whole % 3600 // 60, whole % 60
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def make_sections(meta: dict, last_second: float) -> list[Section]:
    chapters = meta.get("chapters") or []
    if len(chapters) >= MIN_CHAPTERS:
        return [Section(float(c["start_time"]), c.get("title") or "Untitled") for c in chapters]
    duration = max(float(meta.get("duration") or 0), last_second)
    return [Section(float(start), None) for start in range(0, int(duration) + 1, PART_SECONDS)]


def fill_sections(sections: list[Section], segments: list[dict]) -> None:
    index = 0
    current_key, current_words, current_start = None, [], 0.0

    def flush() -> None:
        if current_words:
            sections[current_key[0]].paragraphs.append((current_start, " ".join(current_words)))

    for segment in sorted(segments, key=lambda s: s["startMs"]):
        seconds = segment["startMs"] / 1000
        text = " ".join(segment["text"].split())
        if not text:
            continue
        while index + 1 < len(sections) and seconds >= sections[index + 1].start:
            index += 1
        key = (index, int(seconds // PARAGRAPH_SECONDS))
        if key != current_key:
            flush()
            current_key, current_words, current_start = key, [], seconds
        current_words.append(text)
    flush()


def write_transcript(sections: list[Section], path: Path) -> int:
    lines: list[str] = []
    for position, section in enumerate(sections):
        if not section.paragraphs:
            continue
        end = sections[position + 1].start if position + 1 < len(sections) else None
        heading = section.title or f"Part {position + 1}" + (f" (to {clock(end)})" if end else "")
        section.first_line = len(lines) + 1
        lines.append(f"## [{clock(section.start)}] {heading}")
        lines.extend(f"[{clock(start)}] {text}" for start, text in section.paragraphs)
        section.last_line = len(lines)
    path.write_text("\n".join(lines) + "\n")
    return len(lines)


def make_batches(sections: list[Section]) -> list[list[Section]]:
    batches: list[list[Section]] = [[]]
    for section in sections:
        size = sum(s.words for s in batches[-1])
        if batches[-1] and size + section.words > BATCH_WORDS:
            batches.append([])
        batches[-1].append(section)
    # A short tail is not worth a reader of its own.
    if len(batches) > 1 and sum(s.words for s in batches[-1]) < BATCH_WORDS * SMALL_BATCH_FRACTION:
        batches[-2].extend(batches.pop())
    return batches


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip().splitlines()[-2], file=sys.stderr)
        return 2
    segments = json.loads(Path(sys.argv[1]).read_text())
    meta = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])
    if not segments:
        print("transcript: no segments", file=sys.stderr)
        return 1

    sections = make_sections(meta, segments[-1]["startMs"] / 1000)
    fill_sections(sections, segments)
    line_count = write_transcript(sections, out)
    sections = [s for s in sections if s.paragraphs]
    total_words = sum(s.words for s in sections)
    has_chapters = any(s.title for s in sections)

    print(f"transcript: {out} ({line_count} lines, {total_words} words)")
    kind = "chapters" if has_chapters else f"{PART_SECONDS // 60}-minute parts, the video has no chapters"
    print(f"sections: {len(sections)} ({kind})")
    for number, section in enumerate(sections, start=1):
        title = section.title or "untitled part"
        print(f"  {number}. [{clock(section.start)}] {title} | lines {section.first_line}-{section.last_line}"
              f" | {section.words} words")
    if total_words > LONG_TRANSCRIPT_WORDS:
        batches = make_batches(sections)
        print(f"batches: {len(batches)} (long video: give each batch to its own subagent)")
        for number, batch in enumerate(batches, start=1):
            first, last = sections.index(batch[0]) + 1, sections.index(batch[-1]) + 1
            following = sections[last] if last < len(sections) else None
            end = clock(following.start) if following else "end"
            print(f"  batch {number}: sections {first}-{last} | [{clock(batch[0].start)}] to {end}"
                  f" | lines {batch[0].first_line}-{batch[-1].last_line}"
                  f" | {sum(s.words for s in batch)} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
