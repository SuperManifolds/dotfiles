---
name: song-id
description: Identify a song from an audio file, from whatever a running game or app is playing, or a whole game soundtrack, then find it on YouTube and at a download source. Use whenever the user asks to "shazam" something, "what song is this", "what's the music playing in <game/app>", "identify this track/soundtrack", "track down the soundtrack of <game>", "find this song on YouTube", or "where can I download this track". Fingerprints the audio against Shazam and AudD, guards against the false matches both give on stock/royalty-free music, extracts Ren'Py archives, and verifies YouTube candidates by fingerprint instead of by title. No API keys required.
allowed-tools:
  - Bash(*/identify.py:*)
  - Bash(identify.py:*)
  - Bash(lsof:*)
  - Bash(ffprobe:*)
  - Bash(yt-dlp:*)
  - Bash(uvx --quiet unrpa:*)
  - Read
---

# song-id

Identify a recording and return somewhere to hear and download it. The helper
lives in this skill dir; invoke it by path (`"$CLAUDE_SKILL_DIR/identify.py"`).

```
identify.py [--no-audd] [--jsonl RESULTS] <audio file> [more files ...]
```

It cuts three 15 s clips per file with `ffmpeg`, matches each against Shazam
and one against AudD, and prints a verdict. It is a `uv` script, so its
dependencies resolve on first run. Each run sends 15 s clips to Shazam and
AudD.

For one track follow steps 1 to 6. For a whole soundtrack read
"Whole soundtrack" first; it changes how steps 1 and 3 are run.

## 1. Get the audio as a file

**Do not record.** Output is usually on headphones, so the microphone hears
nothing. Find the file the app is reading instead:

```
ps axo pid,command | grep -i <app name>
lsof -p <pid> | grep -i -E "\.(mp3|ogg|opus|flac|wav|m4a)"
```

Ren'Py games with unarchived assets show the exact track under
`.../autorun/game/audio/`. If the user already gave a file, skip this step.

If the assets are in a Ren'Py archive (`*.rpa` next to the scripts), list and
extract it with `unrpa` into the session scratchpad:

```
uvx --quiet unrpa -l <archive.rpa>                 # list
uvx --quiet unrpa -s -mp <scratch>/<game> <archive.rpa>   # extract
```

`lsof` then only names the archive, so the playing track has to be worked out
from the scripts (see "Where a track plays"). For other archive formats
(`.pak`, Unity bundles) say so and ask; nothing here handles them.

**The filename is evidence.** Developers often keep the track's real title as
the filename with spaces removed (`themariner` is "The Mariner"). Codenames
such as `c1s14_2` or `gaming` carry nothing.

## 2. Read the tags

```
ffprobe -v error -show_entries format_tags -of default=nw=1 <file>
```

Check sibling files in the same folder too. Some carry title and artist, or a
source URL in the comment tag (a YouTube link, a Free Music Archive page).
Archived games usually have every tag stripped.

## 3. Fingerprint

Run `identify.py` on the file and read the `verdict:` line.

| Verdict | Meaning | What to do |
|---|---|---|
| `confirmed` | AudD returned the same title, or the title resembles the filename. | Use it. |
| `consistent` | At least 2 of 3 clips gave the same catalogued Shazam record. | Likely right. Corroborate with duration or a second source before calling it certain. |
| `renamed-release` | Clips agree, but the Shazam record is an orphan: no ISRC, no album, no store link. | Same recording, misleading name. Usually a stock track re-released under another artist. Find the original (below). |
| `weak` | Only one clip matched, or each clip matched something different. | Treat as no match. This is how coincidental matches look. |
| `none` | Shazam matched nothing. | Go to duration matching or other evidence. |

**Fingerprint hits on library music are often wrong.** A sweep of 203 stock
tracks produced 62 Shazam hits; 9 contradicted identifications already
confirmed by the developer, and most of the 36 with no other support were
unrelated commercial songs. Rules that came out of that:

- Never let a fingerprint hit overwrite a developer statement or a tag.
- A hit whose title disagrees with a meaningful filename is suspect.
- A rejected hit is unconfirmed, not disproved. Keep it in an appendix; one
  discarded hit was later proved right by a community source.

**Finding the original behind a renamed release.** AudD often has it: for
"Dj Vigi, The Future Is Bright" (orphan) it returned "QubeSounds, Electronic
Future Beats", which was the Pixabay original. AudD can also return a second
renamed release, so check its answer:

- Its release date must not be later than the game file's own date.
- Prefer the entry whose label is a stock library or the artist's own name
  over one with an unrelated or generic label.
- If still unsure, both names are aliases. Search YouTube for each and let
  step 5 decide.

`audd: error: ...` means the anonymous quota (a few requests per day) is
spent. `AUDD_API_TOKEN` in the environment lifts it.

Note the Shazam `id=` of the local file. Step 5 compares against it.

## 4. Find it on YouTube

Search with the real artist and title:

```
yt-dlp --flat-playlist --print "%(id)s | %(duration_string)s | views=%(view_count)s | %(channel)s | %(title)s" "ytsearch15:<artist> <title>"
```

Keep results whose duration is within a few seconds of the local file's.
Titles that look like `some-track-name-117997` are Pixabay filenames; the
number is the Pixabay id, and the source page is
`https://pixabay.com/music/id-<n>/`.

Third-party "no copyright music" re-uploads are acceptable when the artist
has no upload of their own. Label them as re-uploads.

## 5. Verify

Same title does not mean same recording, and wrong-artist homonyms are common
for generic titles.

**By fingerprint** (proves it is the same recording). For the best two to four
candidates, take a short sample and identify it:

```
yt-dlp -q -f bestaudio --download-sections "*45-62" -x --audio-format mp3 -o "<scratch>/%(id)s.%(ext)s" -- <video id>
identify.py --no-audd <scratch>/<video id>.mp3
```

A candidate is confirmed when its Shazam `id=` equals the local file's. This
works for `renamed-release` records too; the id is what matters, not the name.

**By oEmbed** (proves the link is live and what it is titled). Use this for
every YouTube URL in a long list, and for any URL a subagent reported:

```
curl -s "https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=<id>"
```

A dead or invented link returns an error instead of JSON.

Put samples in the session scratchpad, not in the user's folders.

## 6. Answer

Lead with artist and title, then:

- A **YouTube link**, always. Say which uploads were fingerprint-verified and
  whether they are the artist's own channel or third-party re-uploads.
- A **download source**: the stock library page (Pixabay, Uppbeat, Music Vine,
  Free Music Archive, Epidemic Sound) or the store and streaming links AudD
  returned.
- The file already on disk, with its bitrate. A game's own copy is often
  higher bitrate than YouTube's audio.
- Anything not opened or checked, named as such (for example a library page
  seen only in search results, or licence terms).

## Whole soundtrack

For "identify every song in <game>". Expect a partial result: the best run so
far identified 90 of 206 tracks.

**Inventory first.** Extract everything, then record each file's stem and
exact duration (`identify.py` prints both). Duration is the key for later
steps.

**Gather non-audio evidence before fingerprinting.** It outranks audio:

1. Developer statements. Use the `discord` skill on the game's server and
   search for answers to "what's the song in <scene>" and for which music
   library the developer uses. Ignore general music-sharing chat and personal
   playlists; they are about other music.
2. Tags and source URLs in the files.
3. Filenames that are real titles.
4. Community lists and fan playlists.

**Sweep the audio.** Run in the background; it takes about 10 s per file:

```
identify.py --no-audd --jsonl <scratch>/sweep.jsonl <dir>/*.ogg
```

`--jsonl` appends one record per file and skips files already recorded, so a
stalled or interrupted run resumes by repeating the command. Leave AudD off
for the sweep and spend it on the `renamed-release` and `consistent` records
afterwards. Expect roughly half the files to return `none`.

**Duration-match the rest against stock libraries.** This is what identifies
tracks with generic titles ("Go", "Mood", "Tempest"):

- Search the library for the title and accept a result only when its listed
  duration is within 2 s of the file's. Record the listed duration in every
  row so the match can be audited. Parse `M:SS` as minutes and seconds.
- The library pages need a real browser: use `agent-browser`. Uppbeat's API
  returns 429 to plain HTTP and Pixabay's music search sits behind a bot wall.
  On 2026-08-28 the working Uppbeat search URL was
  `https://uppbeat.io/search?search=<title>&type=music`.
- Do not assume the library. Run a pilot of about 12 tracks across the likely
  libraries, including one with a known answer, and scale the one that hits.
  A developer who thanked Pixabay turned out to use Uppbeat and Music Vine for
  nearly everything.

**When fanning out to subagents**, put these in every brief: report only
artists and URLs actually seen on a page, never invented; include one track
with a known answer as a sanity check; expect misses and do not force a
match; write results to a file with the listed duration per row. Re-check
durations when merging. That guard caught results that leaked between
concurrent browser sessions.

**Stop when** what is left is one-word titles that libraries serve as category
pages, or covers and remixes, which defeat fingerprinting. Do not suggest
sending the developer a list of tracks to identify; they will not answer it.

**Deliver** a markdown document in `~` (for example
`~/<game>-soundtrack.md`) with:

- Totals, and how the list was built and verified.
- Tier 1: identified with a verified YouTube link. Tier 2: identified with an
  artist and source page. Tier 3: in the game, not identified.
- A confidence per row (Confirmed, High, Medium) and where the track plays.
- An appendix of rejected fingerprint hits and open ambiguities.

## Where a track plays

Ren'Py scripts name the music at each cue. With plain `.rpy` files:

```
grep -rn -E "(play|queue) music" <game>/*.rpy
```

Map each hit to the nearest preceding `label` for the scene. If only compiled
`.rpyc` files exist (often inside a `scripts.rpa`), they need decompiling
first. `unrpyc` is the standard tool and is untested here; the earlier session
decoded the files by hand.

## Known dead ends

Skip these; each was tried and failed.

- `/usr/bin/shazam` only generates signature files. It cannot match.
- A self-compiled ShazamKit `SHSession` binary fails with
  `com.apple.ShazamKit Code=202 "Missing entitlements"`. Matching needs a
  signed app with the ShazamKit service.
- `shazamio`'s `track_about` call fails to decode. The record `identify.py`
  prints is all there is.
- Searching YouTube, SoundCloud, iTunes, Deezer or MusicBrainz for an orphan
  Shazam name. Go to AudD first.
- Cutting clips as MP3. `ffmpeg`'s MP3 encoder rejects some `.ogg` sources;
  `identify.py` cuts mono WAV for that reason.
- Running `shazamio` on Python 3.13 or later without `audioop-lts`. The script
  pins 3.12.
- Game credits screens. They rarely list music, and developers often no
  longer know their sources.
