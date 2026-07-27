#!/usr/bin/env bash
# reddit-search.sh — search Reddit and list matching threads (title, subreddit,
# score, comments, URL) as markdown or JSON, using the same headless,
# challenge-passing browser as reddit-read.sh (see browser.sh). Feed any result
# URL to reddit-read.sh to read the full thread.
#
# Usage:  reddit-search.sh <query...> [--sub S] [--sort SORT] [--time T] [--limit N] [--json]
#   --sub S    restrict to a subreddit (with or without leading r/)
#   --sort     relevance|hot|top|new|comments   (default relevance)
#   --time     hour|day|week|month|year|all      (default all)
#   --limit    max results (default 25)
#   --json     emit raw structured JSON instead of markdown

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/browser.sh"      # reddit_open: headless challenge-passing session
SEARCH_JS="$SCRIPT_DIR/search.js"    # in-page search.json fetch
RENDER="$SCRIPT_DIR/render-search.py"  # results -> markdown / raw JSON

QUERY=""
SUB=""
SORT="relevance"
TIME="all"
LIMIT=25
MODE="markdown"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sub)   SUB="$2"; shift 2 ;;
    --sort)  SORT="$2"; shift 2 ;;
    --time)  TIME="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --json)  MODE="json"; shift ;;
    *)       QUERY="${QUERY:+$QUERY }$1"; shift ;;
  esac
done

if [[ -z "$QUERY" ]]; then
  echo "usage: reddit-search.sh <query...> [--sub S] [--sort relevance|hot|top|new|comments] [--time hour|day|week|month|year|all] [--limit N] [--json]" >&2
  exit 2
fi
[[ "$LIMIT" =~ ^[0-9]+$ ]] || { echo "error: --limit must be a positive integer" >&2; exit 2; }
case "$SORT" in relevance|hot|top|new|comments) ;; *) echo "error: bad --sort: $SORT" >&2; exit 2 ;; esac
case "$TIME" in hour|day|week|month|year|all) ;; *) echo "error: bad --time: $TIME" >&2; exit 2 ;; esac

# URL-encode the query, then build the search.json path (subreddit-scoped or global).
Q=$(QUERY="$QUERY" python3 -c 'import os,urllib.parse; print(urllib.parse.quote(os.environ["QUERY"]))')
if [[ -n "$SUB" ]]; then
  SUB="${SUB#r/}"
  SEARCH_PATH="/r/${SUB}/search.json?q=${Q}&restrict_sr=1&sort=${SORT}&t=${TIME}&limit=${LIMIT}&raw_json=1"
  NAV="https://www.reddit.com/r/${SUB}/search/?q=${Q}"
else
  SEARCH_PATH="/search.json?q=${Q}&sort=${SORT}&t=${TIME}&limit=${LIMIT}&raw_json=1"
  NAV="https://www.reddit.com/search/?q=${Q}"
fi

reddit_open "$NAV"

# Seed the search path + human query as page globals (JSON-encoded so quotes in
# the query are safe), then run search.js in-session; render.py-style output.
ENVELOPE=$(
  {
    printf 'globalThis.__REDDIT_SEARCH_URL=%s; globalThis.__REDDIT_QUERY=%s;\n' \
      "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$SEARCH_PATH")" \
      "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$QUERY")"
    cat "$SEARCH_JS"
  } | agent-browser eval --json --stdin
)

MODE="$MODE" python3 "$RENDER" "$ENVELOPE"
