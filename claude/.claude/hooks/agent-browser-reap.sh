#!/usr/bin/env bash
# SessionEnd + SessionStart hook: close agent-browser sessions that no live
# Claude Code session owns. Each Claude instance drives its own isolated
# browser named "claude-<session id>" (see skills/reddit-thread/browser.sh and
# the fish config), and nothing else ever closes it, so headless Chrome
# instances otherwise pile up for weeks.
#   SessionEnd:   close this session's browser, then reap orphans.
#   SessionStart: reap orphans left by sessions that crashed or were killed
#                 (SessionEnd never fires for those).
# A browser counts as orphaned when its session id is not owned by a running
# claude process (per ~/.claude/sessions/<pid>.json) and its daemon has been
# idle for ORPHAN_MIN_AGE_MIN minutes, which spares a browser whose session
# was resumed under a new id. Closes by name only, never `close --all`.
# Best-effort and fail-open: any miss exits 0.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
command -v jq >/dev/null 2>&1 || exit 0
command -v agent-browser >/dev/null 2>&1 || exit 0

ORPHAN_MIN_AGE_MIN=120
claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
ab_dir="$HOME/.agent-browser"

input=$(cat)
event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty')
session=$(printf '%s' "$input" | jq -r '.session_id // empty')

close_session() {
  agent-browser --session "$1" close >/dev/null 2>&1 || true
}

if [ "$event" = "SessionEnd" ] && [ -n "$session" ]; then
  close_session "claude-$session"
  [ -n "${CLAUDE_CODE_SESSION_ID:-}" ] && [ "$CLAUDE_CODE_SESSION_ID" != "$session" ] \
    && close_session "claude-$CLAUDE_CODE_SESSION_ID"
fi

# Session ids owned by a running claude process.
live=" ${session} ${CLAUDE_CODE_SESSION_ID:-} "
for f in "$claude_dir"/sessions/*.json; do
  [ -r "$f" ] || continue
  pid=$(jq -r '.pid // empty' "$f" 2>/dev/null)
  sid=$(jq -r '.sessionId // empty' "$f" 2>/dev/null)
  [ -n "$pid" ] && [ -n "$sid" ] && kill -0 "$pid" 2>/dev/null && live="$live$sid "
done

agent-browser session list 2>/dev/null | grep -oE 'claude-[0-9a-f-]{36}' | while read -r name; do
  sid=${name#claude-}
  case "$live" in *" $sid "*) continue ;; esac
  # Skip anything touched recently (a resumed session may own it under a new id).
  recent=$(find "$ab_dir" -maxdepth 1 -name "$name.*" -mmin -"$ORPHAN_MIN_AGE_MIN" 2>/dev/null | head -1)
  [ -n "$recent" ] && continue
  close_session "$name"
done

exit 0
