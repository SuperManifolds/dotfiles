#!/usr/bin/env bash
# Stop hook: when Claude finishes a turn, if source files changed, run a FAST
# compile check for the affected language(s). On failure, block (decision:block)
# so Claude fixes it before declaring done — enforcing the "verify" rule.
#
# Kept cheap and non-naggy:
#   - only acts in a git repo with dirty source of a supported language
#   - skips unless the code state changed since the last check (content hash,
#     per session) → no run on conversational turns, no re-run on no-op stops
#   - blocks at most once per distinct code state; the built-in 8-block cap is
#     the ultimate backstop against loops
# Fast checks only (no full test suite): cargo check / go build / swift build /
# make. Never blocks on missing tools or outside a git repo (fail-open).
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"

command -v jq >/dev/null 2>&1 || exit 0
input=$(cat)
session=$(printf '%s' "$input" | jq -r '.session_id // "nosession"')

root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root" 2>/dev/null || exit 0

# Files changed vs HEAD (unstaged+staged) plus staged-without-HEAD plus untracked.
changed=$({ git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } | sort -u)
srcre='\.(rs|go|swift|c|h|cc|cpp|cxx|hpp|hh|m|mm)$'
printf '%s\n' "$changed" | grep -qiE "$srcre" || exit 0

# Which languages are dirty?
has() { printf '%s\n' "$changed" | grep -qiE "$1"; }
langs=""
has '\.rs$'                        && langs="$langs rust"
has '\.go$'                        && langs="$langs go"
has '\.swift$'                     && langs="$langs swift"
has '\.(c|h|cc|cpp|cxx|hpp|hh|m|mm)$' && langs="$langs c"

# Content signature of the current code state, scoped to this session.
sig=$({ git diff HEAD 2>/dev/null; printf '%s\n' "$changed" | grep -iE "$srcre" \
        | while IFS= read -r f; do [ -f "$f" ] && { printf '%s\0' "$f"; cat "$f"; }; done; } \
      | shasum -a 256 2>/dev/null | cut -d' ' -f1)
state="${TMPDIR:-/tmp}/claude-stopverify-${session}"
[ -n "$sig" ] && [ "$sig" = "$(cat "$state" 2>/dev/null)" ] && exit 0
[ -n "$sig" ] && printf '%s' "$sig" > "$state"   # mark this state handled (block at most once for it)

fails=""
add_fail() { fails="${fails}"$'\n'"=== $1 ==="$'\n'"$2"; }
run() { # label, command...
  local label=$1; shift
  local out rc
  out=$("$@" 2>&1); rc=$?
  [ $rc -ne 0 ] && add_fail "$label" "$out"
}

for l in $langs; do
  case $l in
    rust)  command -v cargo >/dev/null 2>&1 && [ -f Cargo.toml ] && run "cargo check" cargo check --quiet ;;
    go)    command -v go    >/dev/null 2>&1 && [ -f go.mod ]     && run "go build ./..." go build ./... ;;
    swift) command -v swift >/dev/null 2>&1 && [ -f Package.swift ] && run "swift build" swift build ;;
    c)     if [ -f Makefile ]; then
             if grep -qE '^check:' Makefile; then run "make check" make check
             else run "make" make; fi
           fi ;;
  esac
done

if [ -n "$fails" ]; then
  reason="Verification failed — do not stop yet. Fix these, then continue:${fails}"
  reason=$(printf '%s' "$reason" | tail -c 4000)
  jq -nc --arg r "$reason" '{decision:"block", reason:$r}'
fi
exit 0
