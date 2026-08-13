#!/usr/bin/env bash
# Fast-fail watcher for a GitHub Actions run. Polls per-job status and exits the
# INSTANT any job fails (naming it), or when the whole run completes green — so a
# job that fails in 30s is caught in ~1 poll instead of being masked until a slow
# 30-min job finishes the run.
#
# Usage: watch-run.sh <run-id> [--repo OWNER/REPO] [--interval SECONDS]
# Exit:  0 = all jobs passed · 1 = a job failed/cancelled/timed_out · 2 = bad args
#
# Run it as a BACKGROUND task so you're notified on the terminal state; do NOT use
# `gh run watch` (it blocks on the whole run and hides fast failures, and can exit
# 0 on a transient HTTP 502).

run_id=""
repo=()
interval=20

while [ $# -gt 0 ]; do
  case "$1" in
    --repo) repo=(--repo "$2"); shift 2 ;;
    --interval) interval="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) run_id="$1"; shift ;;
  esac
done

if [ -z "$run_id" ]; then
  echo "usage: watch-run.sh <run-id> [--repo OWNER/REPO] [--interval SECONDS]" >&2
  exit 2
fi

# Deliberately no `set -e`: a transient gh/network blip must not kill the loop.
while true; do
  jobs_json=$(gh run view "$run_id" "${repo[@]}" --json status,jobs 2>/dev/null)
  if [ -n "$jobs_json" ]; then
    failed=$(printf '%s' "$jobs_json" | jq -r \
      '[.jobs[] | select(.conclusion=="failure" or .conclusion=="cancelled" or .conclusion=="timed_out") | .name] | join(", ")')
    if [ -n "$failed" ]; then
      echo "FAILED: $failed"
      printf '%s' "$jobs_json" | jq -r '.jobs[] | "\(.conclusion // "running")  \(.name)"'
      exit 1
    fi
    rstate=$(printf '%s' "$jobs_json" | jq -r '.status')
    if [ "$rstate" = "completed" ]; then
      echo "GREEN — all jobs passed:"
      printf '%s' "$jobs_json" | jq -r '.jobs[] | "\(.conclusion)  \(.name)"'
      exit 0
    fi
  fi
  sleep "$interval"
done
