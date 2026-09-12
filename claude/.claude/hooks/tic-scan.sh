#!/usr/bin/env bash
# Stop hook: when focus mode is on, scan the finished assistant reply for
# sycophancy tics and bounce it (decision:block) so Claude rewrites without them.
# This is the out-of-model backstop: prose rules decay after compaction, a hook
# does not. Off unless ~/.claude/.focus-mode exists.
#
# Loop-safe:
#   - never blocks when stop_hook_active is already set (no block chains)
#   - blocks at most once per identical reply per session (content hash)
#   - the built-in 8-block cap is the final backstop
# Fail-open: any missing tool / unreadable transcript exits 0.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
command -v jq >/dev/null 2>&1 || exit 0

claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
[ -f "$claude_dir/.focus-mode" ] || exit 0

input=$(cat)
# Already inside a block-driven continuation → do not block again.
[ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false')" = "true" ] && exit 0
session=$(printf '%s' "$input" | jq -r '.session_id // "nosession"')
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')
[ -n "$transcript" ] && [ -f "$transcript" ] || exit 0

# Last assistant text block from the transcript (tail keeps it cheap; each JSONL
# line is self-contained, so tailing stays valid input for jq -s).
reply=$(tail -n 400 "$transcript" 2>/dev/null | jq -rs '
  [ .[] | select(.type=="assistant") | .message.content[]? | select(.type=="text") | .text ] | last // empty' 2>/dev/null)
[ -n "$reply" ] || exit 0

# Load the phrase list (fallback to a minimal built-in set if the file is gone).
phrases_file="$claude_dir/tic-phrases.txt"
if [ -f "$phrases_file" ]; then
  phrases=$(grep -vE '^[[:space:]]*(#|$)' "$phrases_file")
else
  phrases=$(printf '%s\n' "you're absolutely right" "you're absolutely correct" "great question")
fi

# Collect every phrase that appears in the reply (case-insensitive).
hits=""
lower_reply=$(printf '%s' "$reply" | tr '[:upper:]' '[:lower:]')
while IFS= read -r p; do
  [ -n "$p" ] || continue
  lower_p=$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')
  case "$lower_reply" in
    *"$lower_p"*) hits="${hits}${hits:+, }\"${p}\"" ;;
  esac
done <<EOF
$phrases
EOF
[ -n "$hits" ] || exit 0

# Block at most once per identical reply per session.
sig=$(printf '%s' "$reply" | shasum -a 256 2>/dev/null | cut -d' ' -f1)
state="${TMPDIR:-/tmp}/claude-ticscan-${session}"
[ -n "$sig" ] && [ "$sig" = "$(cat "$state" 2>/dev/null)" ] && exit 0
[ -n "$sig" ] && printf '%s' "$sig" > "$state"

reason="Focus mode: your reply contains banned tic(s): ${hits}. Rewrite it without them — cut the phrase, keep the content. Do not acknowledge this note or apologize; just deliver the clean version."
jq -nc --arg r "$reason" '{decision:"block", reason:$r}'
exit 0
