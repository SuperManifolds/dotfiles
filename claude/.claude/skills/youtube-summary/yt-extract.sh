#!/usr/bin/env bash
# yt-extract.sh — pull everything needed to summarize a YouTube video into one
# directory: metadata + chapters (yt-dlp), a timestamped transcript split into
# sections, and optionally the frames worth looking at (slides.py).
#
# Transcript chain: creator captions -> auto captions -> audio download + local
# whisper.cpp. Captions that hold little speech or are in the wrong language are
# replaced by the whisper transcript. `summarize` exits 0 with empty content
# when YouTube refuses a request, so every attempt is checked for actual text
# and retried. whisper-cli is run directly because summarize's own whisper path
# discards timestamps.
#
# Usage:
#   yt-extract.sh <url> [--slides] [--max-slides N] [--asr] [--cookies <browser>] [--out <dir>]
#   yt-extract.sh frame <url> <timestamp>... [--cookies <browser>] [--out <dir>]
#   yt-extract.sh report <summary.md> [--open]
#
#   --slides      also save the frames worth looking at (downloads the video, <=720p)
#   --max-slides  cap on those frames (default: one per 2 minutes, 8 to 30)
#   --asr         skip captions; transcribe the audio locally with whisper
#   --cookies     browser to borrow cookies from (chrome, firefox, safari, ...) for
#                 age-restricted or members-only videos
#   --out         output directory (default: ~/.cache/youtube-summary/<video id>)
#   frame         save a video frame at each <timestamp> (seconds, m:ss or h:mm:ss)
#   report        save a Markdown summary as a report folder with a standalone HTML page

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE_ROOT="${YT_SUMMARY_CACHE:-$HOME/.cache/youtube-summary}"
REPORT_ROOT="${YT_SUMMARY_REPORTS:-$HOME/youtube-summaries}"
MODEL_DIR="$HOME/.summarize/cache/whisper-cpp/models"
WHISPER_MODEL="${SUMMARIZE_WHISPER_CPP_MODEL_PATH:-$MODEL_DIR/ggml-large-v3-turbo.bin}"
VAD_MODEL="$MODEL_DIR/ggml-silero-v5.1.2.bin"

CAPTION_TIMEOUT="2m"
FETCH_ATTEMPTS=2             # captions and downloads; YouTube 403s are often transient
RETRY_DELAY_SECONDS=5
AUDIO_FORMAT='bestaudio[vcodec=none]/best'
VIDEO_FORMAT='bv*[height<=720][vcodec^=avc1]/bv*[height<=720]/b'
VIDEO_KEEP_DAYS=7            # downloaded videos are kept this long for frame grabs
DESCRIPTION_CHARS=800

# Captions below this much speech are music cues or noise, not a transcript.
MIN_SPEECH_CHARS_PER_MINUTE=150
MIN_GATED_SECONDS=60         # too short to judge a speech rate

WHISPER_SAMPLE_RATE=16000    # whisper.cpp wants 16 kHz mono PCM
# Speech over music needs a low threshold and generous padding, or word starts get cut.
VAD_THRESHOLD=0.3
VAD_SPEECH_PAD_MS=300
VAD_MIN_SILENCE_MS=500
# The term prompt only takes effect with some context; a small window keeps one
# bad passage from seeding repetition loops in later ones.
WHISPER_CONTEXT_TOKENS=64
PROMPT_MAX_TERMS=12

SECONDS_PER_SLIDE=120
MIN_SLIDES=8
MAX_SLIDES=30

die() { echo "yt-extract: $*" >&2; exit 1; }
note() { echo "yt-extract: $*" >&2; }

usage() {
  sed -n '14,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

require() {
  local tool
  for tool in "$@"; do
    command -v "$tool" >/dev/null || die "missing dependency: $tool"
  done
}

COMMAND="extract"
case "${1:-}" in
  frame|report) COMMAND="$1"; shift ;;
esac
POSITIONAL=()
SLIDES=0
SLIDE_CAP=""
ASR=0
COOKIES=""
OUT=""
OPEN_REPORT=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --slides)     SLIDES=1; shift ;;
    --max-slides) SLIDE_CAP="${2:-}"; [[ "$SLIDE_CAP" =~ ^[1-9][0-9]*$ ]] || usage; shift 2 ;;
    --asr)        ASR=1; shift ;;
    --cookies)    COOKIES="${2:-}"; [[ -n "$COOKIES" ]] || usage; shift 2 ;;
    --out)        OUT="${2:-}"; [[ -n "$OUT" ]] || usage; shift 2 ;;
    --open)       OPEN_REPORT=1; shift ;;
    -h|--help)    usage ;;
    -*)           die "unknown option: $1" ;;
    *)            POSITIONAL+=("$1"); shift ;;
  esac
done
[[ "${#POSITIONAL[@]}" -gt 0 ]] || usage

# ---- report ---------------------------------------------------------------
if [[ "$COMMAND" == "report" ]]; then
  require uv ffmpeg
  REPORT_PATHS="$(uv run --quiet --script "$SKILL_DIR/report.py" "${POSITIONAL[0]}" --out-root "$REPORT_ROOT")" \
    || die "could not build the report"
  echo "$REPORT_PATHS"
  if [[ "$OPEN_REPORT" -eq 1 ]] && command -v open >/dev/null; then
    open "$(tail -1 <<<"$REPORT_PATHS")"
  fi
  exit 0
fi

require yt-dlp summarize jq ffmpeg python3
URL="${POSITIONAL[0]}"
YTDLP_ARGS=(--no-playlist --no-warnings)
if [[ -n "$COOKIES" ]]; then
  YTDLP_ARGS+=(--cookies-from-browser "$COOKIES")
  export SUMMARIZE_YT_DLP_COOKIES_FROM_BROWSER="$COOKIES"
fi

# "754", "12:34" or "1:02:03" -> whole seconds
to_seconds() {
  local value="$1" total=0 part
  [[ "$value" =~ ^[0-9]+(:[0-9]{1,2}){0,2}(\.[0-9]+)?$ ]] || die "bad timestamp: $value"
  value="${value%%.*}"
  IFS=: read -ra parts <<<"$value"
  for part in "${parts[@]}"; do total=$(( total * 60 + 10#$part )); done
  echo "$total"
}

# Video ids are 11 characters; reading one off the URL avoids a network call.
id_from_url() {
  [[ "$1" =~ (v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11}) ]] && echo "${BASH_REMATCH[2]}"
}

# download <what> <format> <output template>: yt-dlp with retries; false if all fail.
download() {
  local what="$1" format="$2" template="$3" attempt
  for (( attempt = 1; attempt <= FETCH_ATTEMPTS; attempt++ )); do
    if yt-dlp "${YTDLP_ARGS[@]}" -q -f "$format" -o "$template" "$URL" 2>"$WORK/download.err"; then
      return 0
    fi
    note "$what download failed (attempt $attempt/$FETCH_ATTEMPTS)"
    (( attempt < FETCH_ATTEMPTS )) && sleep "$RETRY_DELAY_SECONDS"
  done
  return 1
}

cached_video() { find "$1" -maxdepth 1 -name 'video.*' -type f 2>/dev/null | head -1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---- frame ----------------------------------------------------------------
if [[ "$COMMAND" == "frame" ]]; then
  [[ "${#POSITIONAL[@]}" -gt 1 ]] || usage
  FRAME_SECONDS=()
  for timestamp in "${POSITIONAL[@]:1}"; do FRAME_SECONDS+=("$(to_seconds "$timestamp")"); done
  VIDEO_ID="$(id_from_url "$URL")" \
    || VIDEO_ID="$(yt-dlp "${YTDLP_ARGS[@]}" --print id "$URL")" \
    || die "yt-dlp could not resolve $URL"
  OUT="${OUT:-$CACHE_ROOT/$VIDEO_ID}"
  mkdir -p "$OUT/frames"
  # A video kept from slide extraction makes this instant and offline.
  SOURCE="$(cached_video "$OUT")"
  if [[ -z "$SOURCE" ]]; then
    SOURCE="$(yt-dlp "${YTDLP_ARGS[@]}" -g -f "$VIDEO_FORMAT" "$URL" | head -1)"
    [[ -n "$SOURCE" ]] || die "yt-dlp returned no stream URL for $URL"
  fi
  for seconds_at in "${FRAME_SECONDS[@]}"; do
    FRAME_PATH="$OUT/frames/frame_${seconds_at}s.png"
    rm -f "$FRAME_PATH"
    ffmpeg -v error -y -ss "$seconds_at" -i "$SOURCE" -frames:v 1 "$FRAME_PATH" \
      || die "ffmpeg could not grab a frame at ${seconds_at}s"
    [[ -s "$FRAME_PATH" ]] || die "no frame at ${seconds_at}s (past the end of the video?)"
    echo "$FRAME_PATH"
  done
  exit 0
fi

# ---- metadata -------------------------------------------------------------
yt-dlp "${YTDLP_ARGS[@]}" -J --skip-download "$URL" >"$WORK/meta.json" 2>"$WORK/meta.err" \
  || die "yt-dlp could not read $URL: $(tail -2 "$WORK/meta.err" | tr '\n' ' ')
(age-restricted or members-only videos need --cookies <browser>)"

VIDEO_ID="$(jq -r '.id' "$WORK/meta.json")"
DURATION="$(jq -r '.duration // 0 | floor' "$WORK/meta.json")"
LIVE_STATUS="$(jq -r '.live_status // "not_live"' "$WORK/meta.json")"
case "$LIVE_STATUS" in
  is_live|is_upcoming) die "video is $LIVE_STATUS; there is nothing to transcribe yet" ;;
esac

OUT="${OUT:-$CACHE_ROOT/$VIDEO_ID}"
mkdir -p "$OUT"
cp "$WORK/meta.json" "$OUT/meta.json"
find "$CACHE_ROOT" -maxdepth 2 -name 'video.*' -type f -mtime "+$VIDEO_KEEP_DAYS" -delete 2>/dev/null || true

# Creator-written captions exist when a subtitle track matches the spoken language.
HAS_CREATOR_CAPTIONS="$(jq -r '
  ((.language // "en") | split("-")[0]) as $lang
  | [(.subtitles // {}) | keys[] | select(. != "live_chat") | split("-")[0]]
  | any(. == $lang)' "$OUT/meta.json")"
HAS_ANY_CAPTIONS="$(jq -r '
  [(.subtitles // {}), (.automatic_captions // {}) | keys[] | select(. != "live_chat")]
  | length > 0' "$OUT/meta.json")"
# YouTube marks the track its speech recognition produced as "<lang>-orig". If
# that is not the video's language and the creator wrote no captions in it,
# whatever captions exist are recognition run in the wrong language.
CAPTION_LANGUAGE_MISMATCH="$(jq -r '
  ((.language // "") | split("-")[0]) as $lang
  | [(.automatic_captions // {}) | keys[] | select(endswith("-orig")) | split("-")[0]] as $recognized
  | [(.subtitles // {}) | keys[] | select(. != "live_chat") | split("-")[0]] as $creator
  | ($lang // "") != "" and ($recognized | length) > 0
    and ($recognized | index($lang) | not) and ($creator | index($lang) | not)' "$OUT/meta.json")"

# ---- transcript -----------------------------------------------------------
# Both sources write [{startMs, text}, ...].

# Captions via summarize (creator track preferred, else auto-generated).
fetch_captions() {
  local attempt
  for (( attempt = 1; attempt <= FETCH_ATTEMPTS; attempt++ )); do
    if summarize "$URL" --extract --timestamps --json --plain --metrics off \
         --timeout "$CAPTION_TIMEOUT" --youtube web >"$WORK/extract.json" 2>"$WORK/extract.err" \
       && jq -e '(.extracted.transcriptSegments // []) | length > 0' "$WORK/extract.json" >/dev/null; then
      jq '[.extracted.transcriptSegments[] | {startMs, text}]' "$WORK/extract.json" >"$WORK/captions.json"
      return 0
    fi
    note "no captions (attempt $attempt/$FETCH_ATTEMPTS)"
    (( attempt < FETCH_ATTEMPTS )) && sleep "$RETRY_DELAY_SECONDS"
  done
  return 1
}

# Characters of actual speech per minute, ignoring cues like [Music] and (applause).
speech_rate() {
  jq -r --argjson seconds "$DURATION" '
    ([.[].text | gsub("\\[[^\\]]*\\]|\\([^)]*\\)|[♪♫]"; "") | gsub("\\s+"; "") | length] | add // 0)
    * 60 / $seconds | floor' "$1"
}

# Names and jargon from the title and chapters, phrased the way whisper needs
# them to bias its spelling: one short sentence per term.
whisper_prompt() {
  jq -r --argjson max "$PROMPT_MAX_TERMS" --arg apostrophes "'’" '
    def terms:
      [ (.title // ""), ((.chapters // [])[] | .title // "")
        | scan("[\\p{L}\\p{N}]+(?:[-" + $apostrophes + "][\\p{L}\\p{N}]+)*")
        | select(test("\\p{Lu}.*\\p{Lu}|\\p{Ll}\\p{Lu}|\\p{Lu}.*\\p{N}|\\p{N}.*\\p{Lu}")) ]
      | unique | .[0:$max];
    (.channel // .uploader // "") as $channel
    | if ((.language // "en") | startswith("en")) then
        "\(.title // "")\(if $channel != "" then ", by \($channel)" else "" end)."
        + (terms | map(" We discuss \(.).") | join(""))
      else
        "\(.title // ""). \($channel)."
        + (terms | if length > 0 then " " + join(", ") + "." else "" end)
      end' "$OUT/meta.json"
}

# Audio download + local whisper.cpp. Sets WHISPER_ERROR and returns 1 on failure.
transcribe_audio() {
  local prompt args
  WHISPER_ERROR=""
  if ! command -v whisper-cli >/dev/null; then
    WHISPER_ERROR="whisper-cli is missing (brew install whisper-cpp)"; return 1
  fi
  if [[ ! -f "$WHISPER_MODEL" ]]; then
    WHISPER_ERROR="whisper model is missing: $WHISPER_MODEL"; return 1
  fi
  rm -rf "$WORK/audio"
  if ! download audio "$AUDIO_FORMAT" "$WORK/audio/track.%(ext)s"; then
    WHISPER_ERROR="could not download audio: $(tail -2 "$WORK/download.err" | tr '\n' ' ')"; return 1
  fi
  if ! ffmpeg -v error -y -i "$WORK"/audio/track.* -vn -ar "$WHISPER_SAMPLE_RATE" -ac 1 -c:a pcm_s16le \
         "$WORK/speech.wav" 2>"$WORK/ffmpeg.err"; then
    WHISPER_ERROR="ffmpeg could not decode the audio: $(tail -2 "$WORK/ffmpeg.err" | tr '\n' ' ')"; return 1
  fi

  args=(--model "$WHISPER_MODEL" --language auto --max-context "$WHISPER_CONTEXT_TOKENS"
        --no-prints --output-json --output-file "$WORK/whisper")
  if [[ -f "$VAD_MODEL" ]]; then
    args+=(--vad --vad-model "$VAD_MODEL" --vad-threshold "$VAD_THRESHOLD"
           --vad-speech-pad-ms "$VAD_SPEECH_PAD_MS" --vad-min-silence-duration-ms "$VAD_MIN_SILENCE_MS")
  else
    note "silence detection model missing ($VAD_MODEL); whisper may invent lines over music"
  fi
  prompt="$(whisper_prompt)"
  [[ -n "$prompt" ]] && args+=(--prompt "$prompt" --carry-initial-prompt)

  note "transcribing audio with whisper (roughly a minute per hour of audio)"
  if ! whisper-cli "${args[@]}" "$WORK/speech.wav" >/dev/null 2>"$WORK/whisper.err"; then
    WHISPER_ERROR="whisper-cli failed: $(tail -2 "$WORK/whisper.err" | tr '\n' ' ')"; return 1
  fi
  jq '[.transcription[] | {startMs: .offsets.from, text: (.text | ltrimstr(" "))} | select(.text != "")]' \
    "$WORK/whisper.json" >"$WORK/whisper-segments.json"
  if ! jq -e 'length > 0' "$WORK/whisper-segments.json" >/dev/null; then
    WHISPER_ERROR="whisper found no speech"; return 1
  fi
}

HAVE_CAPTIONS=0
CAPTION_PROBLEM=""
CAPTION_RATE=""
if [[ "$ASR" -eq 0 && "$HAS_ANY_CAPTIONS" == "true" ]] && fetch_captions; then
  HAVE_CAPTIONS=1
  if [[ "$CAPTION_LANGUAGE_MISMATCH" == "true" ]]; then
    CAPTION_PROBLEM="they are not in the spoken language ($(jq -r '.language' "$OUT/meta.json"))"
  elif [[ "$DURATION" -ge "$MIN_GATED_SECONDS" ]]; then
    CAPTION_RATE="$(speech_rate "$WORK/captions.json")"
    if [[ "$CAPTION_RATE" -lt "$MIN_SPEECH_CHARS_PER_MINUTE" ]]; then
      CAPTION_PROBLEM="they hold almost no speech ($CAPTION_RATE characters per minute)"
    fi
  fi
fi
if [[ "$HAS_CREATOR_CAPTIONS" == "true" ]]; then CAPTION_KIND="creator-captions"; else CAPTION_KIND="auto-captions"; fi

TRANSCRIPT_NOTE=""
if [[ "$HAVE_CAPTIONS" -eq 1 && -z "$CAPTION_PROBLEM" ]]; then
  TRANSCRIPT_SOURCE="$CAPTION_KIND"
  cp "$WORK/captions.json" "$WORK/segments.json"
else
  if [[ "$ASR" -eq 1 ]]; then :
  elif [[ -n "$CAPTION_PROBLEM" ]]; then note "doubting $CAPTION_KIND: $CAPTION_PROBLEM; checking the audio"
  else note "no usable captions, falling back to the audio"
  fi
  if transcribe_audio; then
    # Sparse captions are only replaced if the audio actually yields more speech;
    # a music video is sparse either way.
    if [[ -n "$CAPTION_RATE" && -n "$CAPTION_PROBLEM" \
          && "$(speech_rate "$WORK/whisper-segments.json")" -le "$CAPTION_RATE" ]]; then
      TRANSCRIPT_SOURCE="$CAPTION_KIND"
      cp "$WORK/captions.json" "$WORK/segments.json"
      TRANSCRIPT_NOTE="the video has little speech ($CAPTION_RATE characters per minute; whisper found no more); rely on the frames"
    else
      TRANSCRIPT_SOURCE="audio-transcription (whisper.cpp $(basename "$WHISPER_MODEL" .bin | sed 's/^ggml-//'))"
      cp "$WORK/whisper-segments.json" "$WORK/segments.json"
      [[ -n "$CAPTION_PROBLEM" ]] && TRANSCRIPT_NOTE="$CAPTION_KIND were rejected because $CAPTION_PROBLEM"
    fi
  elif [[ "$HAVE_CAPTIONS" -eq 1 ]]; then
    TRANSCRIPT_SOURCE="$CAPTION_KIND"
    cp "$WORK/captions.json" "$WORK/segments.json"
    TRANSCRIPT_NOTE="LOW QUALITY: $CAPTION_KIND kept although $CAPTION_PROBLEM, because transcribing the audio failed ($WHISPER_ERROR)"
  else
    die "audio transcription failed: $WHISPER_ERROR"
  fi
fi
if [[ "$DURATION" -ge "$MIN_GATED_SECONDS" && -z "$TRANSCRIPT_NOTE" ]]; then
  FINAL_RATE="$(speech_rate "$WORK/segments.json")"
  if [[ "$FINAL_RATE" -lt "$MIN_SPEECH_CHARS_PER_MINUTE" ]]; then
    TRANSCRIPT_NOTE="the video has little speech ($FINAL_RATE characters per minute); rely on the frames"
  fi
fi

python3 "$SKILL_DIR/transcript.py" "$WORK/segments.json" "$OUT/meta.json" "$OUT/transcript.txt" \
  >"$WORK/transcript.manifest" || die "could not build the transcript (source: $TRANSCRIPT_SOURCE)"

# ---- slides ---------------------------------------------------------------
SLIDES_NOTE="not requested"
if [[ "$SLIDES" -eq 1 ]]; then
  VIDEO_FILE="$(cached_video "$OUT")"
  if [[ -z "$VIDEO_FILE" ]] && download video "$VIDEO_FORMAT" "$OUT/video.%(ext)s"; then
    VIDEO_FILE="$(cached_video "$OUT")"
  fi
  if [[ -z "$SLIDE_CAP" ]]; then
    SLIDE_CAP=$(( DURATION / SECONDS_PER_SLIDE ))
    (( SLIDE_CAP < MIN_SLIDES )) && SLIDE_CAP="$MIN_SLIDES"
    (( SLIDE_CAP > MAX_SLIDES )) && SLIDE_CAP="$MAX_SLIDES"
  fi
  rm -rf "$OUT/slides"
  if [[ -z "$VIDEO_FILE" ]]; then
    SLIDES_NOTE="FAILED: could not download the video: $(tail -2 "$WORK/download.err" | tr '\n' ' ')"
  elif python3 "$SKILL_DIR/slides.py" "$VIDEO_FILE" "$OUT/slides" --max "$SLIDE_CAP" \
         >"$WORK/slides.json" 2>"$WORK/slides.err"; then
    SLIDES_NOTE="$(jq -r 'length' "$WORK/slides.json") (shown = how long each stayed on screen)"
  else
    SLIDES_NOTE="FAILED: $(tail -2 "$WORK/slides.err" | tr '\n' ' ')"
  fi
fi

# ---- manifest -------------------------------------------------------------
{
  jq -r --argjson chars "$DESCRIPTION_CHARS" '
    def pad: tostring | if length < 2 then "0" + . else . end;
    def clock: floor as $s
      | ($s / 3600 | floor) as $h | ($s % 3600 / 60 | floor) as $m
      | "\(if $h > 0 then "\($h):\($m | pad)" else "\($m)" end):\($s % 60 | pad)";
    "title: \(.title)",
    "channel: \(.channel // .uploader // "unknown")",
    "uploaded: \((.upload_date // "") | if length == 8 then "\(.[0:4])-\(.[4:6])-\(.[6:8])" else "unknown" end)",
    "duration: \((.duration // 0) | clock)",
    "language: \(.language // "unknown")",
    "url: https://www.youtube.com/watch?v=\(.id)",
    "description: \((.description // "") | gsub("\\s+"; " ") | .[0:$chars])"
  ' "$OUT/meta.json"
  echo "transcript_source: $TRANSCRIPT_SOURCE"
  [[ -n "$TRANSCRIPT_NOTE" ]] && echo "transcript_note: $TRANSCRIPT_NOTE"
  cat "$WORK/transcript.manifest"
  echo "slides: $SLIDES_NOTE"
  if [[ "$SLIDES" -eq 1 && -s "$WORK/slides.json" ]]; then
    jq -r '
      def pad: tostring | if length < 2 then "0" + . else . end;
      def clock: . as $s
        | ($s / 3600 | floor) as $h | ($s % 3600 / 60 | floor) as $m
        | "\(if $h > 0 then "\($h):\($m | pad)" else "\($m)" end):\($s % 60 | pad)";
      .[] | "  [\(.seconds | clock)] \(if .shownSeconds > 0 then "shown \(.shownSeconds | clock)" else "gap sample" end) | \(.path)"' "$WORK/slides.json"
  fi
} | tee "$OUT/manifest.txt"
