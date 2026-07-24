#!/usr/bin/env bash
# PostToolUse(Edit|Write): format the just-edited file by extension.
# Silent and non-blocking — always exits 0 so formatting never fails a tool call.
# Each formatter auto-discovers the project's own config (rustfmt.toml,
# .clang-format, .swift-format, biome.json/.prettierrc) when present.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"

f=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$f" ] && [ -f "$f" ] || exit 0

# JS/TS: prefer the repo's own formatter (correct config + version), then a
# global biome/prettier. Skips silently if none is available.
js_fmt() {
  local d; d=$(dirname "$f")
  while [ "$d" != "/" ]; do
    if [ -x "$d/node_modules/.bin/biome" ];   then "$d/node_modules/.bin/biome" format --write "$f" >/dev/null 2>&1; return; fi
    if [ -x "$d/node_modules/.bin/prettier" ]; then "$d/node_modules/.bin/prettier" --write "$f" >/dev/null 2>&1; return; fi
    d=$(dirname "$d")
  done
  if   command -v biome    >/dev/null 2>&1; then biome format --write "$f" >/dev/null 2>&1
  elif command -v prettier >/dev/null 2>&1; then prettier --write "$f"     >/dev/null 2>&1
  fi
}

case "$f" in
  *.rs)                                          command -v rustfmt >/dev/null 2>&1 && rustfmt "$f" 2>/dev/null ;;
  *.go)                                          command -v gofmt   >/dev/null 2>&1 && gofmt -w "$f" 2>/dev/null ;;
  *.swift)                                       xcrun swift-format format -i "$f" 2>/dev/null ;;
  *.c|*.h|*.cc|*.cpp|*.cxx|*.hpp|*.hh|*.m|*.mm)  xcrun clang-format -i "$f" 2>/dev/null ;;
  *.js|*.jsx|*.mjs|*.cjs|*.ts|*.tsx|*.mts|*.cts) js_fmt ;;
esac
exit 0
