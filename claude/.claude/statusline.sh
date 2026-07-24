#!/usr/bin/env bash
# Claude Code status line: model + dir + branch on line 1;
# context bar, cost, effort, and 5h/7d rate limits on line 2.
# Reads session JSON on stdin (see code.claude.com/docs/en/statusline).

input=$(cat)

# Force a UTF-8 locale so box-drawing glyphs render (macOS /bin/bash is 3.2).
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"

# --- ANSI ---
r=$'\033[0m'; dim=$'\033[2m'; bold=$'\033[1m'
green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; cyan=$'\033[36m'; blue=$'\033[34m'

# --- extract fields (defensive: fields may be null/absent early or off-plan) ---
eval "$(jq -r '
  "model=\(.model.display_name // "?" | @sh)",
  "cwd=\(.workspace.current_dir // .cwd // "" | @sh)",
  "ctx_pct=\(.context_window.used_percentage // 0)",
  "ctx_size=\(.context_window.context_window_size // 200000)",
  "cost=\(.cost.total_cost_usd // 0)",
  "effort=\(.effort.level // "" | @sh)",
  "think=\(.thinking.enabled // false)",
  "rl5=\(.rate_limits.five_hour.used_percentage // -1)",
  "rl7=\(.rate_limits.seven_day.used_percentage // -1)"
' <<<"$input")"

# --- line 1: model [·1M] | dir | branch ---
tag="$model"
[ "$ctx_size" -ge 1000000 ] 2>/dev/null && tag="$model${dim}·1M${r}"

line1="${bold}${cyan}${tag}${r}"
if [ -n "$cwd" ]; then
  line1="$line1 ${dim}📁${r} $(basename "$cwd")"
  branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
  [ -n "$branch" ] && line1="$line1 ${dim}🌿${r} ${blue}${branch}${r}"
fi

# --- context bar (10 cells) ---
pct=${ctx_pct%.*}; [ -z "$pct" ] && pct=0
filled=$(( (pct + 5) / 10 )); [ "$filled" -gt 10 ] && filled=10
if   [ "$pct" -ge 85 ]; then cc=$red
elif [ "$pct" -ge 60 ]; then cc=$yellow
else cc=$green; fi
# printf-repeat (not string concat) — bash 3.2 corrupts multibyte var appends.
rep() { [ "$2" -gt 0 ] && printf "$1%.0s" $(seq 1 "$2"); }
bar="$(rep '▓' "$filled")$(rep '░' $((10 - filled)))"

# --- cost ---
costfmt=$(printf '$%.2f' "$cost" 2>/dev/null || echo "\$$cost")

line2="${cc}${bar}${r} ${pct}% ${dim}ctx${r}  ${green}${costfmt}${r}"

# --- effort + thinking ---
[ -n "$effort" ] && line2="$line2  ${dim}${effort}${r}"
[ "$think" = "true" ] && line2="$line2${dim}+think${r}"

# --- rate limits (Pro/Max only, absent early → -1) ---
rlcolor() { if [ "$1" -ge 80 ]; then printf '%s' "$red"; elif [ "$1" -ge 50 ]; then printf '%s' "$yellow"; else printf '%s' "$dim"; fi; }
rl=""
if [ "${rl5%.*}" -ge 0 ] 2>/dev/null; then p=${rl5%.*}; rl="$rl $(rlcolor "$p")5h ${p}%${r}"; fi
if [ "${rl7%.*}" -ge 0 ] 2>/dev/null; then p=${rl7%.*}; rl="$rl ${dim}·${r} $(rlcolor "$p")7d ${p}%${r}"; fi
[ -n "$rl" ] && line2="$line2 ${dim}│${r}$rl"

printf '%s\n%s' "$line1" "$line2"
