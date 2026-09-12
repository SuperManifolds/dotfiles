#!/usr/bin/env bash
# SessionStart hook: when the flag file exists, inject the stricter focus-mode
# ruleset so it survives /clear and /compact. Opt-in and best-effort — any miss
# exits 0 so it never blocks session start.
#   toggle on:  touch ~/.claude/.focus-mode
#   toggle off: rm  ~/.claude/.focus-mode
# Pattern adapted from ayghri/i-have-adhd (MIT).
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
command -v jq >/dev/null 2>&1 || exit 0

claude_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
flag_path="$claude_dir/.focus-mode"
[ -f "$flag_path" ] || exit 0

# Resolve the ruleset next to this script's real location (symlink-safe).
src="${BASH_SOURCE[0]}"
while [ -h "$src" ]; do
  dir=$(cd -P "$(dirname "$src")" && pwd)
  src=$(readlink "$src")
  [ "${src#/}" = "$src" ] && src="$dir/$src"
done
script_dir=$(cd -P "$(dirname "$src")" && pwd)
rules_path="$script_dir/../focus-mode.md"
[ -f "$rules_path" ] || exit 0

# Strip a leading YAML frontmatter block, if present.
body=$(awk '
  NR==1 && $0 ~ /^---[[:space:]]*$/ { fm=1; next }
  fm && $0 ~ /^---[[:space:]]*$/    { fm=0; next }
  !fm { print }
' "$rules_path") || exit 0

ctx="FOCUS MODE ACTIVE (always-on flag: ${flag_path}). The ruleset below applies to every response this session. \"stop focus mode\" turns it off for this session; delete the flag file to disable it for good."$'\n\n'"${body}"

jq -nc --arg c "$ctx" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
exit 0
