#!/usr/bin/env bash
# PostToolUse(Edit|Write): format the just-edited file by extension.
# Silent and non-blocking — always exits 0 so formatting never fails a tool call.
# Each formatter auto-discovers the project's own config (rustfmt.toml,
# .clang-format, .swift-format, .swiftlint.yml, biome.json/.prettierrc) when present.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"

f=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$f" ] && [ -f "$f" ] || exit 0

# Walk up from the edited file looking for any of the named config files.
# Prints the directory containing the first match, or nothing.
find_config_dir() {
  local d; d=$(dirname "$f")
  while [ "$d" != "/" ]; do
    for name in "$@"; do
      [ -e "$d/$name" ] && { printf '%s' "$d"; return; }
    done
    d=$(dirname "$d")
  done
}

# Swift: a project using SwiftLint (.swiftlint.yml) expects SwiftLint's own
# autocorrect, whose conventions (indented switch cases, line length, trailing
# commas, ...) differ from swift-format's opinionated pretty-printer — running
# swift-format there reflows hand-formatted code and breaks the project's lint.
# Prefer `swiftlint --fix` so formatting follows the project; otherwise fall back
# to swift-format, which auto-discovers a .swift-format config when present.
swift_fmt() {
  local cfg; cfg=$(find_config_dir .swiftlint.yml .swiftlint.yaml)
  if [ -n "$cfg" ] && command -v swiftlint >/dev/null 2>&1; then
    local cfg_file="$cfg/.swiftlint.yml"; [ -f "$cfg_file" ] || cfg_file="$cfg/.swiftlint.yaml"
    swiftlint --fix --quiet --config "$cfg_file" "$f" >/dev/null 2>&1
  else
    xcrun swift-format format -i "$f" 2>/dev/null
  fi
}

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
  *.swift)                                       swift_fmt ;;
  *.c|*.h|*.cc|*.cpp|*.cxx|*.hpp|*.hh|*.m|*.mm)  xcrun clang-format -i "$f" 2>/dev/null ;;
  *.js|*.jsx|*.mjs|*.cjs|*.ts|*.tsx|*.mts|*.cts) js_fmt ;;
esac
exit 0
