---
name: review-pr
description: Review the current branch as a pull request, comparing against the base branch. Use when the user asks to review a PR, do a code review, or review changes.
argument-hint: "[base-branch (default: main)]"
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep, Agent, Write
---

Review the current branch against the base branch. The base branch is $ARGUMENTS if provided, otherwise `main`.

The goal is a multi-pass review modeled on ultrareview: gather signals, fan out specialized passes in parallel, then merge findings. Do not skip the fan-out step — single-pass reviews miss issues.

All intermediate artifacts go in `/tmp/review-*` so subagent output stays out of the main context window. The merge step reads them back from disk.

## Step 1: Gather the changeset and stated intent

First, clear any artifacts from a previous run: `rm -f /tmp/review-*.md /tmp/review-diff.patch`.

Then run in parallel:
- `git log --format='%H%n%s%n%n%b%n---' <base>..HEAD` — full commit messages
- `git diff --stat <base>...HEAD`
- `git diff <base>...HEAD > /tmp/review-diff.patch`
- `gh pr view --json title,body,labels 2>/dev/null` if a PR exists for this branch

Write a short `/tmp/review-intent.md` capturing what the author *says* this PR does (from commit messages + PR description). This is checked against the actual diff in Step 5.

## Step 2: Read project conventions

Find and read any of: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.cursorrules`, `.github/pull_request_template.md`, `STYLE.md`. Walk up from the changed files' directories — repos often have nested `CLAUDE.md`.

Write `/tmp/review-conventions.md` with two sections:

1. **Rules** — project-specific conventions relevant to this diff (naming, error-handling patterns, forbidden APIs, required test patterns, etc.). Skip generic advice. If nothing relevant is found, write "no project conventions found" — don't invent any.
2. **Tooling commands** — exact lint/typecheck/test/format commands documented in those files (e.g. `pnpm lint`, `cargo clippy --all-targets`, `pytest tests/unit`). Include any non-obvious flags or pre-steps the docs mention. If the docs don't specify, write "not documented" for that category.

## Step 3: Pre-flight signals

Run the project's real tooling against the diff. The tooling commands captured in `/tmp/review-conventions.md` are the source of truth — use those exact commands when documented. Only fall back to detection when the conventions file says "not documented" for a category, by checking lockfiles and config files (`package.json` scripts, `Cargo.toml`, `pyproject.toml`, `Makefile` targets, `.github/workflows/*` for what CI runs) for what the project actually uses.

Run linters, type checkers, formatters (check mode), and tests in that order. For tests, scope to changed packages/modules if the suite is large.

Capture stdout+stderr to `/tmp/review-signals.md`. Real tooling output is higher-signal than any model pass — failures here are findings, not noise. If a documented tool isn't installed locally, note that in the signals file rather than skipping silently.

Time-box this step to ~3 minutes. If a test suite is too slow, run only the tests that touch changed files.

## Step 4: Fan out specialized review passes

Spawn the following subagents **in parallel** (single message, multiple Agent tool calls). Use `subagent_type: Explore`.

Each subagent prompt must include:
- Pointers to `/tmp/review-diff.patch`, `/tmp/review-intent.md`, `/tmp/review-conventions.md`, `/tmp/review-signals.md`
- Instruction to read full changed files (not just diff hunks) and chase callers/types/config when context is needed
- The specialized charter below
- Output instruction: write findings to `/tmp/review-<pass-name>.md`, one finding per line in the format `path:line — severity — confidence — issue — suggestion`. Confidence is `confident` (the issue is directly visible in the code being read) or `verify` (plausible but depends on assumptions about code/runtime not directly read). Default to `verify` when unsure — over-claiming confidence is the bigger failure mode. No prose, no recap, no preamble.
- Cap at ~15 findings per pass

**Passes:**

1. **security** — secrets, injection (SQL/command/path), auth/authz, crypto misuse, unsafe deserialization, SSRF, insecure defaults, supply-chain risk in new deps.
2. **correctness** — logic errors, off-by-one, error handling that drops failures, missing edge cases, contract violations, wrong assumptions about inputs.
3. **concurrency-resources** — data races, deadlocks, missing synchronization, file/socket/connection leaks, lifetime/ownership bugs, FFI safety.
4. **tests** — coverage gaps for new behavior, brittle assertions, mocked-where-real-needed, tests that pass without exercising the change, missing failure-mode tests.
5. **api-contracts** — breaking changes to public APIs, backward-compat issues, schema/migration risk, mixed dep versions, behavior changes not propagated to callers.
6. **performance** — hot-path allocations, N+1 patterns, unnecessary copies, complexity regressions, sync work in async paths.
7. **whats-missing** — things the diff *should* have changed but didn't. Search for old names that survived a rename, sibling files that look untouched, asymmetric updates (one caller updated, others not), added flags without docs, changed structs without serializer/migration updates, new errors without handlers. This pass is the highest-yield in practice — give it weight.
8. **adversarial** — try to *break* the change. Pathological inputs, empty/null/huge values, concurrent calls, partial failures, network blips mid-operation, malformed config, race against shutdown, what happens on retry. Different framing surfaces different bugs.

## Step 5: Merge, dedupe, and intent-check

Read all `/tmp/review-*.md` files. Then:

1. **Dedupe**: items flagged by multiple passes get a single entry tagged with the pass names (e.g., `[security, correctness]`). Keep the most specific phrasing.
2. **Re-rank**:
   - **High**: memory safety, security holes, data loss, breaking changes, silent failures in critical paths.
   - **Medium**: logic errors, leaks, contract violations, missing validation at boundaries, test gaps for new behavior.
   - **Low**: perf concerns, dead code, misleading names, non-obvious invariants without comments.
3. **Drop noise**: pure style nits unless they cause bugs.
4. **Intent check**: explicitly compare `/tmp/review-intent.md` against the diff. Does the diff actually do what the description claims? Are there changes in the diff *not* mentioned in the intent? Both directions matter — undisclosed scope creep is a finding.
5. **Verification checklist for High findings**: for each remaining High-severity finding, write a concrete verification step — the specific command, test case, manual check, or file/line to inspect that would confirm the issue is real. One per finding. This converts AI claims into actions the user can take. Save to `/tmp/review-verify.md`.

## Step 6: Attempt to reproduce findings

For each finding tagged High, or Medium-with-`verify`-confidence, try to actually produce evidence — confirm or refute it in practice — before presenting. Spawn a single `subagent_type: general-purpose` agent for this step (it needs Bash to run scripts; Explore can't write reproduction files).

The subagent prompt must include:
- Pointer to `/tmp/review-verify.md` and the merged findings list
- Instruction to attempt reproduction for each finding using the most appropriate technique:
  - **Run an existing test** that should fail given the bug.
  - **Write a tiny reproduction script in `/tmp/`** (never inside the repo) and run it — for parsing bugs, off-by-ones, edge cases.
  - **Run the linter/type checker scoped to specific files** if the finding is a static issue.
  - **Grep / read-cross-reference** to confirm structural claims (missing caller, asymmetric update, surviving old name).
  - **Trace through code by hand** when no executable check is feasible — read the involved files end-to-end and write a 2-3 sentence justification.
- Repo modifications are allowed when reproduction genuinely requires them — adding a failing test inside the repo's test directory, instrumenting a function with temporary logging, generating a fixture, etc. Use this leeway when it actually helps, not by default.
- Boundaries that still apply:
  - **Snapshot before mutating.** Run `git status --porcelain` first. If the working tree is dirty (user has uncommitted changes), prefer creating *new* untracked files over modifying tracked ones, so cleanup is unambiguous. If the tree is clean, you have more room to modify and revert.
  - **Always clean up.** Before finishing, restore the working tree to its starting state. New files you created: delete them or move them to `/tmp/`. Tracked files you modified: `git checkout -- <file>`. Verify with `git status --porcelain` matching the snapshot.
  - **No history or remote mutations.** No `git commit`, `git push`, `git reset --hard`, `git rebase`, branch creation/deletion, or anything that touches `.git/` directly.
  - **No network side effects.** Tests and linters that hit the network as part of their normal operation are fine; explicit `curl`/`gh`/API calls to mutate external systems are not.
  - **No destructive shell commands** outside `/tmp/` (`rm -rf`, etc.).
- Record any repo-side artifacts created (and confirm cleanup) in the evidence column of `/tmp/review-reproduced.md`, e.g. `wrote tests/foo_repro_test.py, ran pytest, deleted file`.
- Time-box: ~3 minutes per finding, ~20 minutes total. Spend the time — running a real test or writing a real repro script is the whole point of this step. Skip findings that would require infrastructure not present locally (prod-only configs, external services, real concurrency at scale) and mark them `inconclusive`.
- Output: write `/tmp/review-reproduced.md` with one entry per finding: `path:line — [confirmed|refuted|inconclusive] — evidence (command run, test name, grep result, or reasoning)`.

After the subagent returns, read `/tmp/review-reproduced.md` and update the merged findings:
- **confirmed** findings: drop any `(verify)` tag, promote to `confident`.
- **refuted** findings: remove from the report entirely (they go in a small "ruled out" appendix instead).
- **inconclusive** findings: keep, retain `(verify)` tag, note why reproduction wasn't feasible.

## Step 7: Present the review

1. **One-line summary** of what the changes do.
2. **Intent vs diff** — only if there's a mismatch worth surfacing.
3. **Pre-flight tooling results** — concise: passed / failed / skipped, with failure summaries.
4. **Findings by severity** (High / Medium / Low):
   - `path/to/file.ext:line` — issue — suggestion
   - Append `[security, whats-missing]` etc. when multiple passes raised it.
   - Append `(verify)` to findings whose underlying confidence is `verify` rather than `confident`.
   - Append `(reproduced)` to findings confirmed in Step 6 with concrete evidence — these are the most actionable.
5. **Verification checklist** — for each High finding not already reproduced, the concrete check from `/tmp/review-verify.md`. Skip this section if every High finding was reproduced or there are none.
6. **Ruled out** — short list of findings the reproduction step refuted, one line each, so the user can see what was considered and why it's not a real issue.
7. **Coverage notes** — anything un-reviewable (generated files, vendored code, files too large to read).
8. **Positive notes** — briefly call out what's done well.

Do NOT:
- Skip the fan-out step and review everything yourself in one pass.
- Summarize what every file does.
- Suggest refactors unrelated to the changes.
- Recommend adding docs/comments to unchanged code.
- Flag style preferences unless they cause bugs.
