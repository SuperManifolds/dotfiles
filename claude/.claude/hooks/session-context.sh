#!/usr/bin/env bash
# SessionStart hook: inject a concise snapshot of live repo / PR-CI / cluster
# state so every session starts grounded — instead of Claude running git status
# mid-task. Adaptive (infra lines only for infra repos), best-effort, and cheap.
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
command -v jq >/dev/null 2>&1 || exit 0

lines=""
add() { lines="${lines}${lines:+$'\n'}- $1"; }

root=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -n "$root" ] && cd "$root" 2>/dev/null; then
  branch=$(git branch --show-current 2>/dev/null); [ -n "$branch" ] || branch="(detached)"
  ab=""
  if up=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
    read -r behind ahead <<<"$(git rev-list --left-right --count "${up}...HEAD" 2>/dev/null)"
    ab=" (↑${ahead:-0} ↓${behind:-0} vs ${up})"
  fi
  dirty=$(git status --porcelain 2>/dev/null | grep -c .)
  add "Repo $(basename "$root") on ${branch}${ab} — ${dirty} uncommitted file(s)"
  last=$(git log -1 --format='%h %s' 2>/dev/null); [ -n "$last" ] && add "Last commit: ${last}"

  # Open PR for this branch + CI rollup (best-effort; needs gh + network).
  if command -v gh >/dev/null 2>&1; then
    pr=$(gh pr view --json number,title,state,statusCheckRollup 2>/dev/null)
    if [ -n "$pr" ] && [ "$pr" != "null" ]; then
      prline=$(printf '%s' "$pr" | jq -r '
        (.statusCheckRollup // []) as $c |
        "PR #\(.number) (\(.state|ascii_downcase)): \(.title)" +
        (if ($c|length)==0 then " — no checks"
         else " — checks: " + ($c | map(.conclusion // .status // .state // "PENDING" | ascii_downcase)
              | group_by(.) | map("\(length) \(.[0])") | join(", ")) end)' 2>/dev/null)
      [ -n "$prline" ] && add "$prline"
    fi
  fi

  # Infra context only for infra-ish repos (keeps other sessions noise-free).
  files=$(git ls-files 2>/dev/null)
  if printf '%s\n' "$files" | grep -qiE '(^|/)(Dockerfile|docker-compose[^/]*\.ya?ml|compose\.ya?ml)$'; then
    if command -v docker >/dev/null 2>&1; then
      names=$(docker ps --format '{{.Names}}' 2>/dev/null)
      if [ -n "$names" ]; then
        n=$(printf '%s\n' "$names" | grep -c .)
        add "Docker: ${n} running ($(printf '%s' "$names" | paste -sd, - | sed 's/,/, /g'))"
      fi
    fi
  fi
  if printf '%s\n' "$files" | grep -qiE '(^|/)(Chart\.yaml|kustomization\.ya?ml|helmfile[^/]*\.ya?ml)$|(^|/)(charts|k8s|kube|manifests|deploy)/'; then
    if command -v kubectl >/dev/null 2>&1; then
      kctx=$(kubectl config current-context 2>/dev/null)
      if [ -n "$kctx" ]; then
        kns=$(kubectl config view --minify -o jsonpath='{..namespace}' 2>/dev/null | awk '{print $1}')
        add "Kube context: ${kctx}${kns:+ (ns: ${kns})}"
      fi
    fi
  fi
fi

[ -n "$lines" ] || exit 0
ctx="Live session context (auto-injected at start):"$'\n'"${lines}"
jq -nc --arg c "$ctx" '{hookSpecificOutput:{hookEventName:"SessionStart",additionalContext:$c}}'
exit 0
