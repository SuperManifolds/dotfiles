#!/usr/bin/env bash
# Verify the Neovim config across languages by opening a representative file for
# each in a headless nvim, waiting for LSP servers to attach and validate their
# config, then reporting errors from lazy / LSP / notifier / :messages.
#
# Portable: scaffolds its own fixtures in a temp dir (incl. minimal Cargo/Go
# projects so those servers start). No external project checkout required.
#
# Usage:   nvim/.config/nvim/scripts/verify.sh [--keep] [--only lang1,lang2]
# Exit:    0 if every language is CLEAN, 1 if any real error is found.
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DUMP="$here/verify.lua"
WS="$(mktemp -d "${TMPDIR:-/tmp}/nvim-verify.XXXXXX")"
KEEP=0
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --keep) KEEP=1 ;;
    --only) ONLY="$2"; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done
cleanup() { [ "$KEEP" -eq 1 ] || rm -rf "$WS"; }
trap cleanup EXIT

# ---- scaffold fixtures -------------------------------------------------------
mkdir -p "$WS/rustproj/src" "$WS/goproj" "$WS/tsproj" "$WS/plain"

cat > "$WS/rustproj/Cargo.toml" <<'EOF'
[package]
name = "verify-fixture"
version = "0.1.0"
edition = "2021"
EOF
cat > "$WS/rustproj/src/main.rs" <<'EOF'
fn main() {
    let stations = vec!["central", "harbor", "airport"];
    println!("{} stations", stations.len());
}
EOF

cat > "$WS/goproj/go.mod" <<'EOF'
module verify-fixture

go 1.22
EOF
cat > "$WS/goproj/main.go" <<'EOF'
package main

import "fmt"

func main() {
	stations := []string{"central", "harbor", "airport"}
	fmt.Printf("%d stations\n", len(stations))
}
EOF

cat > "$WS/tsproj/tsconfig.json" <<'EOF'
{ "compilerOptions": { "strict": true, "target": "ES2022", "module": "ESNext" } }
EOF
cat > "$WS/tsproj/client.ts" <<'EOF'
interface Station { id: string; name: string; stops: number; }

export function busiest(stations: Station[]): Station | undefined {
  return stations.sort((a, b) => b.stops - a.stops).at(0);
}
EOF

cat > "$WS/plain/main.py" <<'EOF'
import json
from pathlib import Path


def load_config(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)
EOF
cat > "$WS/plain/config.json" <<'EOF'
{ "name": "orm-updater", "interval_hours": 24, "targets": ["orm.sorlie.io"] }
EOF
cat > "$WS/plain/compose.yaml" <<'EOF'
services:
  portainer:
    image: portainer/portainer-ce:latest
    ports:
      - "9443:9443"
EOF
cat > "$WS/plain/settings.toml" <<'EOF'
[package]
name = "nimbyscript-lsp"
version = "0.3.1"
EOF
cat > "$WS/plain/deploy.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ssh "alex@152.53.156.229" 'docker compose pull && docker compose up -d'
EOF
cat > "$WS/plain/main.tf" <<'EOF'
resource "docker_container" "caddy" {
  name  = "caddy"
  image = "caddy:2"
}
EOF
cat > "$WS/plain/Dockerfile" <<'EOF'
FROM debian:13-slim
RUN apt-get update && apt-get install -y ca-certificates
ENTRYPOINT ["/usr/local/bin/server"]
EOF
cat > "$WS/plain/index.html" <<'EOF'
<!DOCTYPE html>
<html lang="en"><head><title>ORM</title></head><body><h1>OpenRailwayMap</h1></body></html>
EOF
cat > "$WS/plain/style.css" <<'EOF'
:root { --accent: #c81e3a; }
body { margin: 0; color: var(--accent); }
EOF
cat > "$WS/plain/query.sql" <<'EOF'
SELECT station_name, COUNT(*) AS stops
FROM timetable
GROUP BY station_name;
EOF
cat > "$WS/plain/notes.md" <<'EOF'
# A Line Schedule

- 44 shifts across two depots
EOF

# ---- language -> fixture map (label|file|wait_ms) ----------------------------
tests=(
  "rust|$WS/rustproj/src/main.rs|16000"
  "go|$WS/goproj/main.go|16000"
  "typescript|$WS/tsproj/client.ts|12000"
  "lua|$here/verify.lua|9000"
  "python|$WS/plain/main.py|10000"
  "json|$WS/plain/config.json|8000"
  "yaml|$WS/plain/compose.yaml|9000"
  "toml|$WS/plain/settings.toml|9000"
  "bash|$WS/plain/deploy.sh|9000"
  "terraform|$WS/plain/main.tf|12000"
  "dockerfile|$WS/plain/Dockerfile|9000"
  "html|$WS/plain/index.html|10000"
  "css|$WS/plain/style.css|9000"
  "sql|$WS/plain/query.sql|9000"
  "markdown|$WS/plain/notes.md|8000"
)

reports="$WS/reports"; mkdir -p "$reports"
summary="$WS/summary.txt"; : > "$summary"
fail=0

echo "Verifying Neovim config across languages (workspace: $WS)"
for entry in "${tests[@]}"; do
  IFS='|' read -r label file wait_ms <<< "$entry"
  [ -n "$ONLY" ] && [[ ",$ONLY," != *",$label,"* ]] && continue
  [ -f "$file" ] || { printf "%-12s SKIP (missing fixture)\n" "$label" | tee -a "$summary"; continue; }
  out="$reports/$label.out"
  ( cd "$(dirname "$file")" && VERIFY_OUT="$out" VERIFY_WAIT="$wait_ms" \
      nvim --headless "$file" -c "luafile $DUMP" -c "qa!" >/dev/null 2>&1 )
  verdict=$(grep -E "^VERDICT=" "$out" 2>/dev/null | cut -d= -f2)
  tshl=$(grep -E "^TS_HIGHLIGHT_ACTIVE=" "$out" 2>/dev/null | cut -d= -f2)
  lsp=$(grep -E "^LSP_CLIENTS=" "$out" 2>/dev/null | cut -d= -f2)
  notes=$(grep -E "^NOTES=" "$out" 2>/dev/null | cut -d= -f2)
  printf "%-12s %-11s ts_hl=%-5s notes=%-2s lsp=%s\n" \
    "$label" "${verdict:-NO_OUTPUT}" "$tshl" "${notes:-?}" "$lsp" | tee -a "$summary"
  [[ "$verdict" == CLEAN ]] || fail=1
done

echo
if [ "$fail" -ne 0 ]; then
  echo "=== ERROR DETAIL ==="
  for out in "$reports"/*.out; do
    grep -q "^VERDICT=CLEAN" "$out" && continue
    echo "----- $(basename "$out" .out) -----"
    grep -E "^FILE=|^ERR |^VERDICT=" "$out"
  done
  echo
  echo "RESULT: errors found."
else
  echo "RESULT: all languages CLEAN (benign single-file/env notes are counted, not failed)."
fi
[ "$KEEP" -eq 1 ] && echo "(fixtures kept at $WS)"
exit "$fail"
