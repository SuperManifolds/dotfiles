#!/usr/bin/env bash
# SessionStart + CwdChanged hook: bridge mise's per-directory environment
# (toolchain PATH + [env] vars from .mise.toml/.tool-versions) into Claude's
# Bash tool. That tool runs under `sh -c`, so it misses the mise activation the
# interactive fish shell applies — meaning project-pinned tool versions and env
# wouldn't take effect. Writing `export` lines to $CLAUDE_ENV_FILE fixes it:
# Claude Code sources that file as a preamble before every Bash command.
#
# Safe no-op if CLAUDE_ENV_FILE is unset (older Claude Code) or mise is absent.
[ -n "$CLAUDE_ENV_FILE" ] || exit 0
command -v mise >/dev/null 2>&1 || exit 0

# mise is scoped to work projects only (the global mise config is intentionally
# empty). Bridge its environment into the Bash tool only when the current
# directory tree declares a mise config; otherwise clear the file so mise never
# influences personal/non-work sessions.
dir="$PWD"
while :; do
  if [ -e "$dir/.mise.toml" ] || [ -e "$dir/mise.toml" ] || [ -e "$dir/.tool-versions" ]; then
    # `mise env` resolves the environment for the current working directory,
    # independent of interactive-shell activation.
    mise env -s bash 2>/dev/null > "$CLAUDE_ENV_FILE"
    exit 0
  fi
  [ "$dir" = "/" ] && break
  dir="$(dirname "$dir")"
done

: > "$CLAUDE_ENV_FILE"
exit 0
