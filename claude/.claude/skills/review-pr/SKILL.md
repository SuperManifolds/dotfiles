---
name: review-pr
description: Multi-pass review of the current branch as a pull request against a base branch — fans out parallel specialized passes, then merges, reproduces, and reports findings by severity. Manual-only: invoke with `/review-pr [base-branch]`.
argument-hint: "[base-branch (default: main)]"
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep, Agent, Write
---

Review the current branch against the base branch. The base branch is $ARGUMENTS if provided, otherwise `main`.

The goal is a multi-pass review modeled on ultrareview: gather signals, fan out specialized passes in parallel, then merge findings. Do not skip the fan-out step — single-pass reviews miss issues.

All intermediate artifacts go in a per-run directory under `/tmp` (created in Step 1, referred to as `<dir>` below) so subagent output stays out of the main context window. The merge step reads them back from disk.

## Step 1: Gather the changeset and stated intent

First, create a fresh directory for this run's artifacts. A unique directory keeps concurrent reviews — multiple worktrees, repos, or branches running this skill at once — from clobbering each other's files (and avoids an `rm /tmp/review-*` that would wipe another run already in progress):

```
mktemp -d "${TMPDIR:-/tmp}/review-XXXXXXXX"
```

This prints a path like `/tmp/review-a1b2c3d4`. Shell state doesn't persist between commands, so note that path and substitute it literally wherever this skill writes `<dir>/…` below — don't rely on an environment variable surviving across steps.

**Resolve an up-to-date base ref before diffing.** A stale local `main` makes the diff show commits that are already merged upstream, producing phantom findings. Refresh the base from the remote and compare against the remote-tracking ref — never the local branch, which may be checked out or have uncommitted changes:

1. Pick the remote: `git remote` — prefer `origin`, else the first listed. If there is no remote (purely local repo), skip the fetch and use the local base branch as-is.
2. Fetch only the base branch: `git fetch <remote> <base>`. Don't fetch all refs, and don't `checkout`/`pull`/fast-forward the local branch — fetching updates the remote-tracking ref (`<remote>/<base>`) without mutating the working tree or any local branch.
3. Set the comparison base for the rest of this skill: use `<remote>/<base>` when the fetch succeeded, otherwise fall back to the local `<base>`. If the fetch failed (offline, no such remote branch), note in the final output (Step 7) that the review compared against a possibly-stale local base. Everywhere below, `<base>` means this resolved ref.

Then run in parallel:
- `git log --format='%H%n%s%n%n%b%n---' <base>..HEAD` — full commit messages
- `git diff --stat <base>...HEAD`
- `git diff <base>...HEAD > <dir>/diff.patch`
- `gh pr view --json title,body,labels 2>/dev/null` if a PR exists for this branch

Write a short `<dir>/intent.md` capturing what the author *says* this PR does (from commit messages + PR description). This is checked against the actual diff in Step 5.

## Step 2: Read project conventions

Find and read any of: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.cursorrules`, `.github/pull_request_template.md`, `STYLE.md`. Walk up from the changed files' directories — repos often have nested `CLAUDE.md`.

Write `<dir>/conventions.md` with two sections:

1. **Rules** — project-specific conventions relevant to this diff (naming, error-handling patterns, forbidden APIs, required test patterns, etc.). Skip generic advice. If nothing relevant is found, write "no project conventions found" — don't invent any.
2. **Tooling commands** — exact lint/typecheck/test/format commands documented in those files (e.g. `pnpm lint`, `cargo clippy --all-targets`, `pytest tests/unit`). Include any non-obvious flags or pre-steps the docs mention. If the docs don't specify, write "not documented" for that category.

## Step 3: Pre-flight signals

Run the project's real tooling against the diff. The tooling commands captured in `<dir>/conventions.md` are the source of truth — use those exact commands when documented. Only fall back to detection when the conventions file says "not documented" for a category, by checking lockfiles and config files (`package.json` scripts, `Cargo.toml`, `pyproject.toml`, `Makefile` targets, `.github/workflows/*` for what CI runs) for what the project actually uses.

Run linters, type checkers, formatters (check mode), and tests in that order. For tests, scope to changed packages/modules if the suite is large.

Capture stdout+stderr to `<dir>/signals.md`. Real tooling output is higher-signal than any model pass — failures here are findings, not noise. If a documented tool isn't installed locally, note that in the signals file rather than skipping silently.

Time-box this step to ~3 minutes. If a test suite is too slow, run only the tests that touch changed files.

## Step 4: Fan out specialized review passes

Spawn the following subagents **in parallel** (single message, multiple Agent tool calls). Use `subagent_type: Explore`.

Each subagent prompt must include:
- Pointers to `<dir>/diff.patch`, `<dir>/intent.md`, `<dir>/conventions.md`, `<dir>/signals.md`
- Instruction to read full changed files (not just diff hunks) and chase callers/types/config when context is needed
- The specialized charter below
- Output instruction: write findings to `<dir>/<pass-name>.md`, one finding per line in the format `path:line — kind — severity — confidence — description — suggestion`.
  - **kind** is `issue`, `design`, or `style`:
    - `issue` — the code is broken, risky, or has a downside the author probably didn't intend (regardless of whether the line *looks* deliberately written). Bugs that look intentional are still issues. A convention violation that affects correctness or safety (e.g. "always parameterize queries", "always check this error") is an `issue`, not `style`. **Scope:** an issue must either (a) be on a line the diff actually adds/modifies, or (b) name a *specific causal link* to the diff — e.g. a new caller introduced by this PR now reaches a pre-existing weakness with attacker-controlled input. Pre-existing code that the diff merely sits next to (same file, nearby function, same module) is **out of scope**. If you notice something worth flagging in unchanged code, save it for "coverage notes" instead of issues.
    - `design` — the code does what the author intended, the choice is internally consistent, but the reviewer would have made a different one. Only raise where there's a concrete trade-off worth discussing — not matters of taste or naming preference. If `<dir>/conventions.md` documents the choice, divergence is `style` or `issue`, not `design`.
    - `style` — code style and idiom: naming, formatting, ordering, language idioms, comment/doc style, magic numbers, function length. Code works correctly and the author didn't make a meaningful design choice — it's just *how* the code is written. Prefer concrete references to the convention being violated (e.g. "CONTRIBUTING.md says snake_case for modules"). Don't flag style on lines the diff didn't touch.
    - When unsure between `issue` and `design`, prefer `issue`. When unsure between `design` and `style`, prefer `style`.
  - **confidence** is `confident` (directly visible in the code being read) or `verify` (plausible but depends on assumptions about code/runtime not directly read). Default to `verify` when unsure — over-claiming confidence is the bigger failure mode. Style findings are almost always `confident`.
  - No prose, no recap, no preamble.
- Cap at ~15 findings per pass, with at most ~3 `design` and ~5 `style` of those

**Passes:**

1. **security** — secrets, injection (SQL/command/path), auth/authz, crypto misuse, unsafe deserialization, SSRF, insecure defaults, supply-chain risk in new deps.
2. **correctness** — logic errors, off-by-one, error handling that drops failures, missing edge cases, contract violations, wrong assumptions about inputs.
3. **concurrency-resources** — data races, deadlocks, missing synchronization, file/socket/connection leaks, lifetime/ownership bugs, FFI safety.
4. **tests** — coverage gaps for new behavior, brittle assertions, mocked-where-real-needed, tests that pass without exercising the change, missing failure-mode tests.
5. **api-contracts** — breaking changes to public APIs, backward-compat issues, schema/migration risk, mixed dep versions, behavior changes not propagated to callers.
6. **performance** — hot-path allocations, N+1 patterns, unnecessary copies, complexity regressions, sync work in async paths.
7. **whats-missing** — things the diff *should* have changed but didn't. Search for old names that survived a rename, sibling files that look untouched, asymmetric updates (one caller updated, others not), added flags without docs, changed structs without serializer/migration updates, new errors without handlers. This pass is the highest-yield in practice — give it weight.
8. **adversarial** — try to *break* the change. Pathological inputs, empty/null/huge values, concurrent calls, partial failures, network blips mid-operation, malformed config, race against shutdown, what happens on retry. Different framing surfaces different bugs.
9. **style** — focused pass for `style`-kind findings only. Compare changed code against the conventions in `<dir>/conventions.md` and the surrounding code's existing idioms. Look for: naming (case, prefixes, suffixes), formatting deviations the formatter would catch, magic numbers, comment/doc style, ordering (imports, fields, methods), language idioms (e.g. `Result` vs panic, `Option` vs null, `for…of` vs `forEach`). Don't flag style on lines the diff didn't touch. Don't raise `issue` or `design` from this pass — those belong to the other passes.

## Step 5: Merge, dedupe, and intent-check

Read all `<dir>/*.md` files. Then:

1. **Dedupe**: items flagged by multiple passes get a single entry tagged with the pass names (e.g., `[security, correctness]`). Keep the most specific phrasing.
2. **Re-rank**:
   - **High**: memory safety, security holes, data loss, breaking changes, silent failures in critical paths.
   - **Medium**: logic errors, leaks, contract violations, missing validation at boundaries, test gaps for new behavior.
   - **Low**: perf concerns, dead code, misleading names, non-obvious invariants without comments.
3. **Drop noise**: pure style nits unless they cause bugs. Also apply a **blast-radius filter** before keeping any finding at Medium or higher: in the realistic worst case for this codebase, does harm actually accumulate? A 1KB temp file in `/tmp/` that systemd-tmpfiles wipes, a leak on a path that's hit once per process lifetime, a race that the use case forecloses — all are technically real but practically zero. Drop them, or downgrade to Low if there's still a maintainability angle. The test: if you can't articulate concrete harm — "this fills the disk over N hours", "this corrupts user data on retry", "this fires on every request" — the severity is wrong.

   Also drop findings that name pre-existing code the diff didn't touch (see Step 4's `issue` scope rule). If a pass surfaced one, it leaked through; move it to coverage notes or omit.
4. **Split by kind**: write `issue`-kind findings to `<dir>/issues.md`, `design`-kind to `<dir>/design.md`, and `style`-kind to `<dir>/style.md`. Issues drive verification, reproduction, and the main presentation. Design and style are separate output — neither is reproduced or verified. For design points, drop any item only one pass raised at low severity — almost always taste, not signal. For style, dedupe aggressively (the formatter pass and the dedicated style pass will overlap), and group near-duplicates into one entry where possible (e.g. "use snake_case for module names" with multiple file references rather than one entry per file).
5. **Intent check**: explicitly compare `<dir>/intent.md` against the diff. Does the diff actually do what the description claims? Are there changes in the diff *not* mentioned in the intent? Both directions matter — undisclosed scope creep is an `issue`.
6. **Verification checklist for High issues**: for each remaining High-severity issue (not design point), write a concrete verification step — the specific command, test case, manual check, or file/line to inspect that would confirm the issue is real. One per issue. These checks seed Step 6's reproduction for the High issues, and back the Step 7 checklist for any that Step 6 can't settle. Save to `<dir>/verify.md`.

## Step 6: Attempt to reproduce findings

For **every** `issue`-kind finding — all severities, not just High/Medium — try to actually produce evidence to confirm or refute it in practice before presenting. Design and style findings are not reproduced (they're trade-offs and presentation, not falsifiable claims). Spawn a single `subagent_type: general-purpose` agent for this step (it needs Bash to run scripts; Explore can't write reproduction files).

The subagent prompt must include:
- Pointer to `<dir>/issues.md` (every issue-kind finding — attempt all of them) and `<dir>/verify.md` (the concrete pre-written checks for the High ones)
- Instruction to attempt reproduction for each finding using the most appropriate technique:
  - **Run an existing test** that should fail given the bug.
  - **Write a tiny reproduction script in `<dir>/`** (never inside the repo) and run it — for parsing bugs, off-by-ones, edge cases.
  - **Run the linter/type checker scoped to specific files** if the finding is a static issue.
  - **Grep / read-cross-reference** to confirm structural claims (missing caller, asymmetric update, surviving old name).
  - **Trace through code by hand** when no executable check is feasible — read the involved files end-to-end and write a 2-3 sentence justification.
- Repo modifications are allowed when reproduction genuinely requires them — adding a failing test inside the repo's test directory, instrumenting a function with temporary logging, generating a fixture, etc. Use this leeway when it actually helps, not by default.
- Boundaries that still apply:
  - **Snapshot before mutating.** Run `git status --porcelain` first. If the working tree is dirty (user has uncommitted changes), prefer creating *new* untracked files over modifying tracked ones, so cleanup is unambiguous. If the tree is clean, you have more room to modify and revert.
  - **Always clean up.** Before finishing, restore the working tree to its starting state. New files you created: delete them or move them to `<dir>/`. Tracked files you modified: `git checkout -- <file>`. Verify with `git status --porcelain` matching the snapshot.
  - **No history or remote mutations.** No `git commit`, `git push`, `git reset --hard`, `git rebase`, branch creation/deletion, or anything that touches `.git/` directly.
  - **No network side effects.** Tests and linters that hit the network as part of their normal operation are fine; explicit `curl`/`gh`/API calls to mutate external systems are not.
  - **No destructive shell commands** outside `/tmp/` (`rm -rf`, etc.).
- Record any repo-side artifacts created (and confirm cleanup) in the evidence column of `<dir>/reproduced.md`, e.g. `wrote tests/foo_repro_test.py, ran pytest, deleted file`.
- Time-box: ~3 minutes per finding. Attempt every issue; work highest-severity first so that if you run long, only the lowest-severity findings are left unattempted. Spend the time — running a real test or writing a real repro script is the whole point of this step. Skip findings that would require infrastructure not present locally (prod-only configs, external services, real concurrency at scale) and mark them `inconclusive`.
- Output: write `<dir>/reproduced.md` with one entry per finding: `path:line — [confirmed|refuted|inconclusive] — evidence (command run, test name, grep result, or reasoning)`.

After the subagent returns, read `<dir>/reproduced.md` and update the merged findings:
- **confirmed** findings: drop any `(verify)` tag, promote to `confident`.
- **refuted** findings: remove from the report entirely.
- **inconclusive** findings: keep, retain `(verify)` tag, note why reproduction wasn't feasible.

## Step 7: Present the review

1. **One-line summary** of what the changes do.
2. **Intent vs diff** — only if there's a mismatch worth surfacing.
3. **Pre-flight tooling results** — concise: passed / failed / skipped, with failure summaries.
4. **Issues by severity** (High / Medium / Low) — these are bugs, risks, and likely-unintended consequences:
   - `path/to/file.ext:line` — issue — suggestion
   - Append `[security, whats-missing]` etc. when multiple passes raised it.
   - Append `(verify)` to findings whose underlying confidence is `verify` rather than `confident`.
   - Append `(reproduced)` to findings confirmed in Step 6 with concrete evidence — these are the most actionable.
5. **Design notes** — separate, deliberately subordinate section. These are choices the author appears to have made intentionally that the review would push back on. Frame each as a question or trade-off, not a directive: `path:line — what the choice is — what the trade-off is — alternative the author may want to consider`. Skip this section if there are no design notes after Step 5's filtering. Make clear in the section header that these are debate points, not problems to fix.
6. **Code style** — separate, even-more-subordinate section. These are surface-level style and idiom items: naming, formatting, magic numbers, comment style, ordering, language idioms. One bullet per item: `path:line — what — convention or idiom violated`. Group repeated violations into a single entry with multiple file refs. Header should make clear this is "style nits, not blockers" — many users skip this section, and that's fine.
7. **Verification checklist** — for each High issue Step 6 left `inconclusive` (reproduction wasn't feasible locally), the concrete check from `<dir>/verify.md` so the user can confirm it by hand. Confirmed and refuted issues don't appear here. Skip this section if no High issue is inconclusive.
8. **Coverage notes** — anything un-reviewable (generated files, vendored code, files too large to read).

Do NOT:
- Skip the fan-out step and review everything yourself in one pass.
- Summarize what every file does.
- Suggest refactors unrelated to the changes.
- Recommend adding docs/comments to unchanged code.
- Flag style preferences unless they cause bugs.
