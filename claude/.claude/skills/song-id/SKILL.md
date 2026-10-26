---
name: song-id
description: Identify a song from an audio file, from whatever a running game or app is playing, or a whole game soundtrack, then find it on YouTube and at a download source. Use whenever the user asks to "shazam" something, "what song is this", "what's the music playing in <game/app>", "identify this track/soundtrack", "track down the soundtrack of <game>", "find this song on YouTube", "where can I download this track", or "what played during <scene>". Fingerprints the audio against Shazam and AudD, guards against the false matches both give on stock/royalty-free music, searches stock libraries (Storyblocks, stockmusic.net, iTunes) by title, composer and duration, proves every candidate by comparing its audio with the local file, extracts Ren'Py archives and maps each track to the scenes it plays in. No API keys required.
allowed-tools:
  - Bash(*/identify.py:*)
  - Bash(identify.py:*)
  - Bash(*/compare.py:*)
  - Bash(compare.py:*)
  - Bash(*/libsearch.py:*)
  - Bash(libsearch.py:*)
  - Bash(*/cues.py:*)
  - Bash(cues.py:*)
  - Bash(lsof:*)
  - Bash(ffprobe:*)
  - Bash(yt-dlp:*)
  - Bash(uvx --quiet unrpa:*)
  - Read
---

# song-id

Identify a recording and return somewhere to hear and download it. The
helpers live in this skill dir; invoke them by path
(`"$CLAUDE_SKILL_DIR/identify.py"`). They are `uv` scripts, so dependencies
resolve on first run.

| Helper | Does |
|---|---|
| `identify.py [--no-audd] [--clips N] [--jsonl RESULTS] <files>` | Prints embedded tags, matches N clips (default 3) against Shazam and the middle one against AudD, prints a verdict. Sends 15 s clips to both services. |
| `compare.py [--jobs N] <local file> <candidates>` | Compares the audio of each candidate (file, preview URL or YouTube id) with the local file. **The proof** that two recordings are the same. |
| `libsearch.py <library> ...` | Searches Storyblocks, stockmusic.net, iTunes and Deezer by title, artist and duration; lists Storyblocks by length alone; dumps stockmusic.net's catalogue for duration sweeps; `preview` turns a Spotify or Deezer link into a 30 s preview URL. Recipes for other libraries: `libraries.md`. |
| `cues.py --music DIR --out CUES.json <scripts>` | Every music cue in Ren'Py scripts with the dialogue under it, for "where does this play". |

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

`identify.py` prints them on its `tags:` line. By hand:

```
ffprobe -v error -show_entries format_tags:stream_tags -of default=nw=1 <file>
```

**Ask for stream tags too.** Ogg Vorbis keeps its tags on the stream, so
`format_tags` alone prints nothing for `.ogg` files. That once made a whole
soundtrack look stripped when 130 of its 206 files carried tags.

Check sibling files in the same folder too. What the tags gave away:

| Tag | Meaning |
|---|---|
| `title`, `artist`, `album` | The answer, or the composer to search. A title that differs from the filename is usually the release title (`italian.ogg`: title=Black Baugette, artist=Will Rees, on Storyblocks). |
| `comment` with a URL | The source page (a YouTube link, a Free Music Archive page). |
| `TSRC` (an ISRC), `n=Converted by SpotiDownloader.com` | Ripped from Spotify. Find the artist's YouTube "Topic" upload. |
| `encoder=Lavc…` | Files converted in one batch share it, so it groups files by source. In Realm Invader all 42 Storyblocks matches were `Lavc60.37`, all 35 stockmusic.net matches `Lavc59.44`, and the `Lavc59.43` files were YouTube and Spotify releases (AudD's territory). Once a few files of one group are identified, search the rest of the group in the same library first. |
| A DAW name (`REAPER`, `Logic Pro X`, `Pro Tools`) | The composer's own export. A hint for which composer to sweep, not proof: REAPER pointed to Jon Presstone for six tracks and to someone else for a seventh. |
| `genre=Blues`, `date=2005`, an `IENG` name | stockmusic.net's legacy collections. |

## 3. Fingerprint

Run `identify.py` on the file and read the `verdict:` line.

| Verdict | Meaning | What to do |
|---|---|---|
| `confirmed` | AudD returned the same title, or the title resembles the filename. | Use it. |
| `consistent` | At least 2 clips gave the same catalogued Shazam record. | Likely right. Corroborate with duration or a second source before calling it certain. |
| `renamed-release` | Clips agree, but the Shazam record is an orphan: no ISRC, no album, no store link. | Same recording, misleading name. Usually a stock track re-released under another artist. Find the original (below). |
| `weak` | Only one clip matched, or each clip matched something different. | Treat as no match. This is how coincidental matches look. |
| `none` | Shazam matched nothing. | Try `--clips 8`, then library search ("Whole soundtrack"). |

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

`audd: error: ...` means the anonymous quota (about ten requests per day) is
spent. `AUDD_API_TOKEN` in the environment lifts it.

**AudD knows what Shazam does not.** Indie releases on streaming services
(no-copyright YouTube channels, small Spotify labels) are often missing from
Shazam but present in AudD. On 7 Realm Invader leftovers that every library
sweep had missed, one AudD clip each identified 5, generic labels included
("Ragtime", "The Blues", "Piano 1", "Suspense"). AudD answers with Spotify and
Deezer links; get their 30 s previews with `libsearch.py preview <link>` and
prove the hit with `compare.py`. A Spotify length equal to the file's to the
millisecond is a strong sign; a region-restricted track has no preview.

**No match on 3 clips is not the end.** `--clips 8` identified 4 of 117
tracks that 3 clips had missed. Check what it names, though: one track came
back under an alias artist ("Melodia Alegre" for Ehrling's "Lounge"). Find
the real upload and prove it with `compare.py`.

Note the Shazam `id=` of the local file. Step 5 can compare against it.

## 4. Find it on YouTube

Search with the real artist and title:

```
yt-dlp --flat-playlist --print "%(id)s | %(duration_string)s | views=%(view_count)s | %(channel)s | %(title)s" "ytsearch15:<artist> <title>"
```

Keep results whose duration is within a few seconds of the local file's, or
longer: game files are often trimmed.
Titles that look like `some-track-name-117997` are Pixabay filenames; the
number is the Pixabay id, and the source page is
`https://pixabay.com/music/id-<n>/`.

Third-party "no copyright music" re-uploads are acceptable when the artist
has no upload of their own. Label them as re-uploads.

For a track found in a library, search YouTube for the title with the
composer, the library's artist name and the "Topic" channel. Uploads often
credit a different name than the library does (Dave Von Beck's "Counting On
You" is on "F.U.s - Topic"), so let `compare.py` decide. 56 of the 100
library matches in Realm Invader had no YouTube upload at all; the library
page is then the answer.

## 5. Verify

Same title does not mean same recording, and wrong-artist homonyms are common
for generic titles. Same duration does not either.

**By audio comparison** (proves it is the same recording). This is the main
check, and the only one for library tracks Shazam does not know:

```
compare.py <local file> <candidate> [more candidates ...]
```

A candidate is a local file, a direct audio URL (a library preview) or a
YouTube id. It fetches up to 7 minutes of each and prints one line per
candidate:

| Line | Median BER | Meaning |
|---|---|---|
| `MATCH` | under 0.30 | Same recording. True matches score 0.04-0.15; watermarked previews and lossy re-uploads up to about 0.25. |
| `PARTIAL` | one block under 0.30 | Same composition, different version: the instrumental of a vocal mix (0.21-0.30), a single stem (0.29), an edit or a loop. Look for the sibling version (`libraries.md`: Storyblocks sets, neighbouring stockmusic.net UPCs). |
| `no match` | about 0.47 | Unrelated. |

On a real match the three blocks share one `shift`. A 30 s store preview and a
game file trimmed from a longer track both still match; `compare.py` takes its
blocks from the shorter side. An artist's own upload can score `PARTIAL` while
re-uploads `MATCH` (a different master), so test more than one upload.

Before trusting it in a new environment, run it once on a pair with a known
answer and expect `MATCH`.

**By Shazam id** (for commercial tracks Shazam knows). For the best two to
four candidates, take a short sample and identify it:

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

- A **YouTube link** when one exists. Say which uploads were verified (by
  `compare.py` or Shazam id) and whether they are the artist's own channel or
  third-party re-uploads.
- A **download source**: the stock library page (Storyblocks, stockmusic.net,
  Pixabay, Uppbeat, Music Vine, Free Music Archive, Epidemic Sound) or the
  store and streaming links AudD returned.
- The file already on disk, with its bitrate. A game's own copy is often
  higher bitrate than YouTube's audio.
- The `compare.py` line (verdict and median BER) for anything found by
  library search.
- Anything not opened or checked, named as such (for example a library page
  seen only in search results, or licence terms).

## Whole soundtrack

For "identify every song in <game>". Expect a partial result. The best run
identified 201 of 206 Realm Invader tracks: 90 in a first pass (developer
statements, Shazam, title searches on Uppbeat, Music Vine and Pixabay), 101
in a second pass by library search proven with `compare.py` (two libraries
the first pass never searched, Storyblocks and stockmusic.net, held 73 of
them), and 10 in a third pass by AudD and whole-catalogue length sweeps.

**Inventory first.** Extract everything, then record each file's stem, exact
duration and tags (`identify.py` prints all three). Duration is the key for
later steps, and the encoder tag groups files by source.

**Gather non-audio evidence before fingerprinting.** It outranks audio:

1. Developer statements. Use the `discord` skill on the game's server and
   search for answers to "what's the song in <scene>" and for which music
   library the developer uses. Ignore general music-sharing chat and personal
   playlists; they are about other music.
2. Tags and source URLs in the files (step 2 above).
3. Filenames that are real titles.
4. Community lists and fan playlists.

**Sweep the audio.** Run in the background; it takes about 10 s per file:

```
identify.py --no-audd --jsonl <scratch>/sweep.jsonl <dir>/*.ogg
```

`--jsonl` appends one record per file and skips files already recorded, so a
stalled or interrupted run resumes by repeating the command. Leave AudD off
for the sweep: spend it on the `renamed-release` and `consistent` records,
and above all on the files still unidentified after the library search
below. Expect roughly half the files to return `none`. Run the files
that stay unidentified once more with `--clips 8` and a new `--jsonl` file.

**Search the libraries for the rest.** A candidate counts only when
`compare.py` says `MATCH`. Titles and durations narrow the search; they never
decide it. In order of yield:

1. **Title search in every likely library.** `libsearch.py storyblocks
   "<title>"`, `libsearch.py stockmusic "<title>"`, plus the libraries in
   `libraries.md`. Game files are often trims or loops of the release (Tango
   is 2:00 of a 2:34 track, Reminisce 2:57 of 3:15), so for a distinctive
   title test the top two or three results whatever their length. Do not
   assume the library: run a pilot of about 12 tracks across the likely
   libraries, including one with a known answer, and scale the one that hits.
   A developer who thanked Pixabay turned out to use Uppbeat and Music Vine
   for nearly everything, and later Storyblocks and stockmusic.net for half of
   the rest.
2. **Hidden versions.** A `PARTIAL`, or a title hit that does not match, often
   means another mix: list the Storyblocks set (`--set`) and the neighbouring
   stockmusic.net UPCs and compare each version. The game used vocal mixes,
   instrumentals, "full loops" and backtracks. When a set holds only stems,
   the game file may be all of them played together: mix them
   (`ffmpeg -i a.mp3 -i b.mp3 -i c.mp3 -filter_complex amix=inputs=3:normalize=0 mix.wav`)
   and compare the mix. Life Ahead's three stems scored 0.29 to 0.47 alone
   and 0.066 mixed.
3. **Composer sweeps.** Developers reuse a few composers. Once two or more
   tracks match one composer, list that composer's catalogue
   (`libsearch.py storyblocks --artist <portal id> --dur <s> --tol 3`,
   `libsearch.py catalog <dump> --artist "<name>" --dur <s> --tol 3`) and
   compare everything near each unidentified file's length. Generic labels
   ("disco1", "G-Funk", "Hip Hop (1)") fell to this.
4. **Full-catalogue duration sweep.** Where the whole catalogue can be listed
   by length, compare every track at each leftover file's length:

   ```
   libsearch.py stockmusic-dump <scratch>/stockmusic.jsonl
   compare.py --jobs 8 <file> $(libsearch.py catalog <scratch>/stockmusic.jsonl --dur <s> --tol 0.6 --previews)
   compare.py --jobs 8 <file> $(libsearch.py storyblocks --dur <s> --tol 0.15 --pages 60 --previews)
   ```

   stockmusic.net gives 10 to 50 candidates per file, Storyblocks 30 to 900
   (it lists lengths rounded down to the second; run a second pass with
   `--tol 1.2`, since some versions are listed a second long). This found
   tracks whose game label has nothing to do with the title: "Vineeta Theme"
   is "The Lie of the Land", "DarkMusic2" is "Haunted Shores", "Crystalline"
   is "Crystal". The length listing shows one version per Storyblocks set, so
   alternate versions still need the set expanded (item 2). Envato Elements,
   AudioJungle, Uppbeat and Pixabay can also be listed by length
   (`libraries.md`); in Realm Invader only Pixabay added one.
5. **Duration-filtered mood searches.** Game labels are often not the release
   title ("Solar" is "S.O.L.A.R.", "Aggressive" is "I Can't Stop", "Tribal" is
   "Hell Hath Fury"), so search a mood or genre word with a duration filter:
   `libsearch.py storyblocks horror --dur <s> --tol 1`, and the same on
   YouTube (keep results within a few seconds).
6. **Streaming releases.** `libsearch.py itunes "<title> <artist guess>" --dur
   <s>` and compare its 30 s preview. A Spotify listing with the exact length
   plus Shazam agreement, with no audio to compare, is *likely*, not
   identified.

**When fanning out to subagents** (about 20 tracks each worked well), put
these in every brief:

- `compare.py` is the only proof; report its line for the best candidate.
- A sanity check: one file with a known answer that must print `MATCH`.
- Report only artists and URLs actually seen on a page, never invented.
- What earlier rounds already tried for each track, so it is not repeated.
- A budget of about 12-15 `compare.py` runs per track.
- One JSON line per track with status, artist, title, library URL, YouTube
  URL, BER and notes, written to a file.

Then re-run `compare.py` yourself on every reported match before accepting
it. In the second pass all 100 held, but the check is what makes the result
trustworthy. A second, mop-up round that gives the agents the strategies
that worked in round one found about 30 more. Runs take hours and the network
stalls, so keep every sweep resumable.

**Stop when** each leftover file has had a title search, a composer sweep, a
full-catalogue length sweep in every library that can be listed, `--clips 8`
and one AudD request. What is left is usually tracks from libraries that
cannot be listed, alternate versions hidden in sets, or covers and remixes,
which defeat fingerprinting. Do not suggest sending the developer a list of tracks to
identify; they will not answer it.

**Deliver** a markdown document in `~` (for example
`~/<game>-soundtrack.md`) with:

- Totals, and how the list was built and verified.
- Tier 1: identified with a verified YouTube link. Tier 2: identified with an
  artist and source page. Tier 3: in the game, not identified.
- A confidence per row (Confirmed, High, Medium), the `compare.py` BER for
  library matches, and the game label next to the real title when they
  differ.
- A scene index (next section), so "what played when X happened" can be
  answered later.
- An appendix of rejected fingerprint hits and open ambiguities.

## Where a track plays

Ren'Py scripts name the music at each cue. `cues.py` lists every cue with its
label, channel, tracks and the dialogue under it:

```
cues.py --music <extracted>/audio/music --out <scratch>/cues.json <story scripts in story order>
```

It reads plain `.rpy` files or, when only compiled `.rpyc` files exist (often
inside a `scripts.rpa`), the `pseudo/*.rpy.txt` sources that the
`renpy-walkthrough` skill's `rpw.py dump` rebuilds. It resolves `define
audio.x` aliases, playlists, `<from N>` offsets and music played on `sound`
channels, and it drops ambience and effects by keeping only cues that name a
file in `--music`. The excerpt runs linearly, so it can cross into a choice
branch; check the script when a description depends on it.

**Scene index.** For "what played during <scene>" questions, batch the cues
(about 50 each) to subagents with a brief: for each cue write where, who, what
happens in one or two sentences, keywords (kiss, fight, date, funeral and so
on, named plainly) and mood, using only the given dialogue. Merge into one
table row per cue, in story order, with the `script:line` id. Answer later
questions by searching that table for a character plus an event.

Main menu music is not a story cue. It is set in screens or by
`config.main_menu_music`, often switched by persistent flags as chapters are
finished, so read the menu screens for it.

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
- Accepting a library hit on title and duration alone. Same-length,
  same-title tracks by other artists are common; only `compare.py` decides.
- Exact-title sweeps for files whose label is not the release title. Use
  composer, catalogue and mood-plus-duration sweeps (Whole soundtrack).
- Driving Storyblocks with `agent-browser` (403) and Pixabay in any browser
  (Cloudflare challenge). Recipes that work: `libraries.md`.
- Trusting a stockmusic.net "full" dump read in one order. The API stops at
  page 416 (9,984 tracks of about 12,100); `libsearch.py stockmusic-dump`
  reads both orders.
