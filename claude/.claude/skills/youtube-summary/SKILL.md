---
name: youtube-summary
description: Summarize a YouTube video reliably from its real transcript and on-screen slides. Use whenever the user gives a youtube.com / youtu.be URL and wants a summary, notes, key takeaways, an outline, "what does this video say about X", or a transcript; also for "is this video worth watching" and "tl;dw". Fetches metadata, chapters and a timestamped transcript (creator captions, then auto-captions, then local whisper transcription of the audio when captions are missing or useless), and saves the frames worth looking at so on-screen content (slides, code, charts, demos) makes it into the summary. Handles multi-hour videos by splitting them across subagents, and can save the result as a Markdown + HTML report. Fully local, no API keys.
allowed-tools:
  - Bash(*/yt-extract.sh:*)
  - Bash(yt-extract.sh:*)
  - Read
  - Write
  - Agent
---

# youtube-summary

Claude cannot watch video. This skill turns a YouTube URL into text and images
Claude can read, then summarizes from those — never from the title, the
description, or memory of the video.

The helper lives in this skill dir; invoke it by path
(`"$CLAUDE_SKILL_DIR/yt-extract.sh"`).

## 1. Extract

```
yt-extract.sh <url> [--slides] [--max-slides N] [--asr] [--cookies <browser>] [--out <dir>]
```

It prints a manifest (also saved as `manifest.txt`) and writes everything to
`~/.cache/youtube-summary/<video id>/`:

- `transcript.txt` — a `## [time] title` heading per section, then one
  paragraph per ~30 s, each starting with its `[m:ss]`
- `slides/slide_NNN_<seconds>s.png` — with `--slides`
- `meta.json` — full yt-dlp metadata

**Pass `--slides` by default.** It takes about 10 s per hour of video. Leave it
off only when the visuals clearly carry nothing (podcast, interview, talking
head, music) or the user wants just a quick gist.

### What the manifest tells you

`transcript_source` says how far to trust the text:

| Value | Meaning |
|---|---|
| `creator-captions` | Written by the uploader. Punctuated, names usually right. |
| `auto-captions` | YouTube speech recognition. No punctuation; names, jargon and numbers are often misheard. |
| `audio-transcription (…)` | The audio was transcribed locally with whisper, because captions were missing, nearly empty, or in the wrong language. Accurate and punctuated. Whisper is primed with terms from the title and chapters, which fixes most names but can over-apply a spelling (e.g. write an unrelated word in the capitals of an acronym from the title); over music it may echo the title. |

`transcript_note`, when present, is a warning to carry into the Caveats:
captions were rejected and why, the video has little speech (lean on the
frames), or `LOW QUALITY` (bad captions kept because whisper failed).

`sections` lists every chapter with its line range in `transcript.txt` and its
word count. A video without chapters is cut into 15-minute parts.

`slides` are the moments where the picture changed to something new: each
slide in its fully built state, each camera angle once, not a fixed interval.
`shown` is how long that picture stayed on screen; long-shown slides usually
carry the main points. Default cap is one per 2 minutes (8 to 30);
`--max-slides N` overrides it.

`batches` appears only for long videos; see section 4.

Rerun with `--asr` to force whisper (about a minute per hour of audio) if the
transcript still reads as gibberish.

## 2. Read

1. Read `transcript.txt` in full (about 150 lines per hour). If the manifest
   has `batches`, follow section 4 instead of reading it yourself. Never
   summarize from a partial read without saying so.
2. View every slide image listed in the manifest. Use them for what the audio
   does not carry: text on slides, code, charts, diagrams, product shots, and
   the correct spelling of names the captions garbled. Frames that show only
   a face are worth nothing; move on.
3. Look at the video itself whenever the transcript alone leaves you unsure
   what is meant. Grab frames at the timestamps in question (instant when
   `--slides` was used, about 1 s each otherwise; any number per call):

   ```
   yt-extract.sh frame <url> <timestamp>...   # 754, 12:34 or 1:02:03
   ```

   Do this rather than guess when:

   - the speaker refers to something on screen ("as you can see here", "this
     chart", "the code on the left", "these two numbers");
   - a passage is ambiguous or seems to contradict another one;
   - a name, term, figure or formula looks misheard and is probably shown
     on screen;
   - the passage only makes sense with a demo, diagram or comparison you
     cannot see.

   A transcript paragraph spans ~30 s and its timestamp marks the start, so
   for a visual that builds up, sample two or three points across it (for a
   `[12:30]` paragraph: `12:35 12:45 12:58`). If the frame shows a
   transition or does not help, try a few seconds later before giving up.

   Frames count as evidence like slides do: list the useful ones under
   "From the slides" with their timestamp and path.

## 3. Write the summary

Default shape — scale it to the video and to what the user asked for (a
specific question gets a direct answer first, then supporting points):

```markdown
# <title>
<channel> · <uploaded> · <duration> · <url>

**TL;DR** — 2–3 sentences: the thesis and the conclusion.

## Key points
- <claim, specific enough to be useful> ([12:34](https://youtu.be/<id>?t=754))

## Walkthrough            ← videos over ~20 min; one heading per section
### [4:17] <section title>
<2–4 sentences>

## From the slides         ← only slides that add information
- [11:57] <what it shows, including exact on-screen figures> — <image path>

## Caveats
Transcript source: <value>. <transcript_note, anything uncertain or missing>
```

Rules that keep it accurate:

- Every key point carries a timestamp link (`https://youtu.be/<id>?t=<seconds>`)
  taken from the paragraph it came from, so it can be checked. Never estimate
  one.
- State only what the transcript or a slide supports. Attribute opinions and
  predictions to the speaker rather than presenting them as fact.
- Copy numbers, names and quotes exactly. With `auto-captions`, cross-check
  names and terms against the title, description, section titles and slides;
  if a word still looks misheard, write it as heard and flag it.
- Skip sponsor reads, intros and subscribe requests.
- Write in the language the user is using; mention the video's language when
  it differs.

## 4. Long videos

When the manifest has a `batches:` block (transcripts over about 25,000
words, roughly two hours), do not read the transcript yourself. Give each
batch to its own subagent, all launched in one message so they run in
parallel, then write the summary from their notes.

Send each subagent this brief with the placeholders filled in from the
manifest. It must stand alone; the subagent knows nothing else.

```
You are taking notes on one part of a YouTube video. Someone else will write
a summary of the whole video from your notes alone, so they must be specific
and checkable.

Video: <title> — <channel> — <url>
Your part: <batch start> to <batch end>. Its sections:
  <number>. [<start>] <title> (lines <first>-<last>)
  ...

Transcript: <transcript path>. Read lines <batch first line> to <batch last
line> in full (Read with offset and limit). Lines starting with ## are section
headings; every other line starts with the [timestamp] of its paragraph.
Transcript source: <transcript_source>. <one sentence on what that means for
names and numbers>

Frames from your part; view each one with Read:
  [<time>] <path>
  ...
If a passage is unclear or points at something on screen, grab the moment
and look at it:
  <absolute path to yt-extract.sh> frame <url> <timestamp>...

Return, for each section in order:

### [<start>] <title>
- 3 to 8 notes. Each states a specific claim, number, name, argument or
  conclusion, never "they discuss X", and ends with the [timestamp] of the
  paragraph it came from.
- Quotes: at most two, verbatim, with timestamps, only if notable.
- On screen: what the frames add beyond the audio. Omit if nothing.
- Unclear: what you could not resolve. Omit if nothing.

Rules: only what the transcript or a frame supports. Never invent a
timestamp. Attribute opinions to the speaker by name. Skip sponsor reads.
Finish with "Part summary:" and 3 to 4 sentences.
```

Then:

1. Write the summary from the notes: pick key points across the whole video,
   not a fixed number per batch, and keep each note's timestamp.
2. Before presenting, check the claims that carry the summary (the TL;DR and
   the top few key points) against the transcript by reading the paragraphs
   at their timestamps. Notes passed through a subagent can drift.
3. If a subagent failed or returned nothing usable for a batch, read that
   batch yourself rather than leaving a hole; say so if you cannot.

## 5. Save a report

When the user asks to save, export or file the summary, or wants a report or
an HTML page:

1. Write the summary as Markdown to `<output dir>/summary.md` (the directory
   holding `manifest.txt`). Put the useful slides and frames inline where
   they belong, each as `![<time> — <what it shows>](<absolute image path>)`.
2. Run:

   ```
   yt-extract.sh report <output dir>/summary.md [--open]
   ```

It creates `~/youtube-summaries/<title>-<video id>/` holding `summary.md`,
its `images/`, and `summary.html`: one self-contained file with the images
embedded and every timestamp a link that opens YouTube at that moment. It
prints both paths; give them to the user. `--open` also opens the HTML page.

## When it fails

- **`yt-dlp could not read`** — private, removed, region-locked,
  age-restricted or members-only. For the last two, ask the user whether to
  retry with `--cookies <their browser>` (it reads that browser's YouTube
  cookies).
- **Live or upcoming streams** are rejected; wait until the stream has ended.
- **`slides: FAILED`** — summarize from the transcript and say the slides were
  unavailable.
- **Transcript failure after retries** — YouTube intermittently returns 403 on
  downloads; the script already retries, so rerun it once. If it keeps
  failing, the usual cause is an outdated `yt-dlp`; tell the user and suggest
  `brew upgrade yt-dlp summarize`.
- Run extractions one at a time; `--no-playlist` is always applied, so a
  playlist URL yields only the linked video.

Never fall back to summarizing from the title, description or prior knowledge.
If no transcript can be obtained, say that plainly.

## Dependencies

`yt-dlp`, `summarize`, `whisper-cpp`, `ffmpeg`, `jq`, `uv` (Homebrew) and
`python3`. Two whisper models in `~/.summarize/cache/whisper-cpp/models/`:
`ggml-large-v3-turbo.bin` (speech) and `ggml-silero-v5.1.2.bin` (silence
detection), both from Hugging Face (`ggerganov/whisper.cpp`,
`ggml-org/whisper-vad`). The report step fetches the Python `markdown`
package through `uv` on first use.

Downloaded videos are kept in the cache for 7 days so frame grabs stay
instant; transcripts, slides and frames stay until deleted.
Built and tested for YouTube; other sites `yt-dlp` supports are untested.
