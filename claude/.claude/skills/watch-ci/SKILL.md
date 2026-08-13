---
name: watch-ci
description: Watch a GitHub Actions CI run (or a PR's status checks) to completion with fast-fail detection — surface a failing job within seconds instead of after a slow job finishes the whole run. Use whenever you need to monitor a `gh` workflow run / GitHub Actions run / PR checks after pushing a commit, opening a PR, or re-running jobs. Prefer this over `gh run watch`, which blocks until the entire run ends (so a job that fails in 30s stays hidden behind a 30-min build) and can exit 0 on a transient HTTP 502.
allowed-tools:
  - Bash(gh:*)
  - Bash(*/watch-run.sh:*)
  - Bash(watch-run.sh:*)
---

# watch-ci

Monitor a GitHub Actions run so a **fast-failing job is caught in ~1 poll**, not
after the slowest job finishes the run.

## Why not `gh run watch`

- It blocks until the **whole run** reaches a terminal state. If Check/Clippy
  fails in 30s but a Windows build runs 30 min, you don't learn about the failure
  for ~30 min. That's the exact trap this skill exists to avoid.
- It can exit `0` on a transient `HTTP 502` without the run having finished — its
  exit code isn't trustworthy.

## Use it

1. Find the run id for the branch you just pushed (or a PR):

   ```sh
   gh run list --repo OWNER/REPO --workflow ci.yml --branch <branch> --limit 1 --json databaseId --jq '.[0].databaseId'
   ```

2. Launch the watcher as a **background task** (so you're notified on the terminal
   state and can keep working):

   ```sh
   "$CLAUDE_SKILL_DIR/watch-run.sh" <run-id> --repo OWNER/REPO
   ```

   It polls every 20s (`--interval N` to change) and:
   - exits **1** the instant any job is `failure`/`cancelled`/`timed_out`, printing
     which job failed and the full per-job list;
   - exits **0** when the run completes with every job green.

   The background-task completion notification tells you which happened; read the
   task output for the job breakdown.

## React to the result

- **A real job failed** → pull that job's log, find the error, fix, push, then
  re-launch the watcher on the new run:

  ```sh
  JOB=$(gh run view <run-id> --repo OWNER/REPO --json jobs --jq '.jobs[]|select(.name=="<job>")|.databaseId')
  gh api repos/OWNER/REPO/actions/jobs/$JOB/logs | grep -iE "error\[|error:|warning:|FAILED|panicked|-->" | tail -40
  ```

  Mid-run, `gh run view --log-failed` / `gh run view --job <id> --log` may return
  empty until the run finalizes — the `gh api .../jobs/<id>/logs` endpoint works
  while the run is still going.

- **A transient infra failure** (network/download flake, not our code) → re-run
  just the failed job instead of re-pushing, then re-watch the same run:

  ```sh
  gh run rerun <run-id> --repo OWNER/REPO --failed
  ```

  (A run must be in a terminal state to be re-run; if it says "already running",
  wait for it to finish.)

- **Green** → report it and move on.

## Gotchas baked into the script (don't re-derive them)

- **Separate `gh` queries; don't nest `jq` on tab-containing output** — feeding a
  `jq` result that embeds `\t`/newlines into another `jq` throws "Invalid string:
  control characters must be escaped".
- **Don't name a shell variable `status`** — it's read-only in zsh; the script
  uses `rstate`.
- **No `set -e`** — a transient `gh`/network blip must not kill a long poll; the
  loop tolerates an empty response and retries.
