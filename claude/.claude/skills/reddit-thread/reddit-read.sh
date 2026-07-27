#!/usr/bin/env bash
# reddit-read.sh — reliably dump a Reddit discussion thread (post + full comment
# tree) as clean markdown, using a real Chrome via agent-browser to pass Reddit's
# Fastly "js_challenge" bot detection, then fetching the thread's .json from
# inside that authenticated browser session.
#
# Why this works (see SKILL.md): plain curl / .json / old.reddit all return 403,
# and an automated browser is blocked by its "HeadlessChrome" User-Agent and
# navigator.webdriver tells. Overriding the UA header and hiding those tells (via
# the stealth init-script) passes the challenge; once cookies are set, same-origin
# fetch('<permalink>.json') returns the full structured thread.
#
# Usage:  reddit-read.sh <reddit-thread-url> [--json] [--limit N]
#   --json    emit raw structured JSON instead of markdown
#   --limit   max top-level fetch size (default 500)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/browser.sh"    # reddit_open: headless challenge-passing session
EXTRACT="$SCRIPT_DIR/extract.js"   # in-page thread fetch + comment-tree walk
RENDER="$SCRIPT_DIR/render.py"     # structured result -> markdown / raw JSON

URL=""
MODE="markdown"
LIMIT=500
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)  MODE="json"; shift ;;
    --limit) LIMIT="$2"; shift 2 ;;
    *)       URL="$1"; shift ;;
  esac
done

if [[ -z "$URL" ]]; then
  echo "usage: reddit-read.sh <reddit-thread-url> [--json] [--limit N]" >&2
  exit 2
fi

# LIMIT is injected into the page as a JS number, so it must be digits only.
if [[ ! "$LIMIT" =~ ^[0-9]+$ ]]; then
  echo "error: --limit must be a positive integer" >&2
  exit 2
fi

# Normalize to a www.reddit.com comments permalink.
URL="${URL//old.reddit.com/www.reddit.com}"
URL="${URL//np.reddit.com/www.reddit.com}"
if [[ "$URL" != http*://www.reddit.com/* ]]; then
  echo "error: not a reddit thread URL: $URL" >&2
  exit 2
fi

# Open a headless, challenge-passing session on the thread (see browser.sh).
reddit_open "$URL"

# In-session extraction: seed the top-level fetch size as a page global, then
# run extract.js inside the challenge-passed session. Its structured result
# comes back in agent-browser's --json envelope, which render.py turns into
# markdown (or raw JSON when MODE=json).
ENVELOPE=$(
  { printf 'globalThis.__REDDIT_LIMIT=%s;\n' "$LIMIT"; cat "$EXTRACT"; } \
    | agent-browser eval --json --stdin
)

MODE="$MODE" python3 "$RENDER" "$ENVELOPE"
