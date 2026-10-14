---
name: review-pr
description: Multi-pass review of the current branch as a pull request against a base branch, fanning out parallel specialized passes, then merging, reproducing, and reporting findings by severity. Use when asked to review the current branch, a diff, or a change before it ships. Reports findings only, it never posts them; pair with /review-comments for that.
argument-hint: "[base-branch (default: main)]"
allowed-tools: Bash, Read, Glob, Grep, Agent, Write, Skill
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

Write a short `<dir>/intent.md` capturing what the author *says* this PR does (from commit messages + PR description). This is checked against the actual diff in Step 5. Give it three more sections, because each one later decides whether a finding is real:

- **Headline claim**: the one sentence the PR exists to make true ("the image no longer carries any credential", "restore is 14% faster"). Step 3 tests it directly.
- **Deferred**: everything the description says is out of scope or left for later ("Not in this change", "follow-up", "known gap"). A finding that lands in this list is a design question at most.
- **Linked work**: every PR and issue the description or commits reference (`#1277`, `VIRT-350`). Read each with `gh pr view <n> --json title,state,body` and note what it changes. A finding about a gap that a linked, in-flight PR closes is not a finding on this one, and a linked PR's description often states the runtime behaviour a pass will guess at.

## Step 2: Read project conventions

Find and read any of: `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.cursorrules`, `.github/pull_request_template.md`, `STYLE.md`. Walk up from the changed files' directories — repos often have nested `CLAUDE.md`.

Write `<dir>/conventions.md` with two sections:

1. **Rules** — project-specific conventions relevant to this diff (naming, error-handling patterns, forbidden APIs, required test patterns, etc.). Skip generic advice. If nothing relevant is found, write "no project conventions found" — don't invent any.
2. **Tooling commands** — exact lint/typecheck/test/format commands documented in those files (e.g. `pnpm lint`, `cargo clippy --all-targets`, `pytest tests/unit`). Include any non-obvious flags or pre-steps the docs mention. If the docs don't specify, write "not documented" for that category.

## Step 2b: Decide where each check runs

Do this before running anything. The failure it prevents is the most common one in this skill: a suite needs root, x86_64, gVisor, a second kernel or live credentials, the local box can't provide it, and the review records "skipped" and moves on, while a machine that could run it sits idle. The default is the opposite. Every check runs in the environment the change targets, and the local box is just where the cheap checks happen.

1. **Inventory what you have.** Run `uname -m`, `uname -r` and `sudo -n true` locally. Read the available-skills list in your context. The **`x86-root-vm`** skill gives you a root x86_64 VM on `ssh van-0` with docker, runsc and a pinned gVisor, one per worktree, booting in about 17 s. Treat it as available unless `ssh van-0 true` actually fails, and if it does, fix that first (the skill and memory name the usual causes, such as the WireGuard endpoint roaming) before calling anything unrunnable. Note any clusters too (kind, the dev EKS clusters named in the project's instructions) and credential files (`~/*.env`, `gh auth status` scopes).
2. **Classify every check the review will want.** That means the project's test suites, the author's stated test plan, and the headline-claim check. For each one, write down what it needs: root, an architecture, runsc/gVisor, a kernel, docker images, live credentials, a cluster. Anything gVisor checkpoint/restore needs x86_64, because gVisor's arm64 sentry cannot serve the register sets cruise reads. On an arm64 dev box, that means the VM.
3. **Assign each check a place** and write the table to `<dir>/environments.md`: `check — needs — runs on — how`. For VM checks, load the `x86-root-vm` skill now (Skill tool) and copy into `<dir>/environments.md` the concrete recipe this review will use: the VM name (`wt-<worktree>`, created and started with `vmctl` if it doesn't exist), its port, the two-hop ssh/scp pattern, the cross-compile commands, the mirrored source path, the env vars the suites need (`CRUISE_BIN`, `CRUISE_OVERLAY_ROOT`, `TMPDIR=/var/tmp/...`, `PATH` including `/usr/sbin`), and the marker-file pattern for waiting on long jobs. Subagents do not see the skills list, so this file is how they learn the VM exists and how to drive it.
4. **Start the VM now** if any check needs it, so it is ready by Step 3. Stop it by name when the review is done.

A check may be recorded as **not run** only after you tried it in its assigned environment and it failed for a named reason you could not fix, such as a credential nobody has, or a cluster that's down. "Needs root", "needs x86", "runsc not installed", "image not present" and "no credentials in the environment" are not reasons. They are instructions about where to run it or what to fetch first. If an input is genuinely missing, ask the user for that one thing rather than skipping.

## Step 3: Pre-flight signals

Run the project's real tooling against the diff. The tooling commands captured in `<dir>/conventions.md` are the source of truth — use those exact commands when documented. Only fall back to detection when the conventions file says "not documented" for a category, by checking lockfiles and config files (`package.json` scripts, `Cargo.toml`, `pyproject.toml`, `Makefile` targets, `.github/workflows/*` for what CI runs) for what the project actually uses.

Run linters, type checkers, formatters (check mode), and tests in that order. For tests, scope to changed packages/modules if the suite is large.

Capture stdout+stderr to `<dir>/signals.md`. Real tooling output is higher-signal than any model pass — failures here are findings, not noise. Run each check where `<dir>/environments.md` assigned it, not only where you happen to be. Read every SKIP in the output: a test that skipped because of the local box (no python3 when the fixtures were built, no root, wrong arch, no runsc) gets rerun in an environment that can run it before it is written down, and the signals file says which environment produced each result.

Time-box this step to ~3 minutes. If a test suite is too slow, run only the tests that touch changed files.

**Then start the author's own test plan where it targets, in the background.** The time box covers the fast local tooling only. It is not a reason to skip the slow suites that matter most. Read the PR's testing section and commit messages for the suites the author ran, and especially for any they say were *not* rerun ("not run since the merge", "root rows not rerun"). Those are the highest-value checks in the review, because they are the ones nobody has run against this exact tree. Start them now on the environment the change targets (a VM, another architecture, a cluster), using the skills and hosts available, so they run while Step 4 fans out. Detect completion with a marker file the job writes on exit (`echo $? > done`), never with `pgrep -f` over ssh, which matches its own command line and reports a finished job as running.

Also test the **headline claim** from `<dir>/intent.md` against what the build actually produces, not against the code that is supposed to produce it. If the claim is "the image carries no credential", build the image and grep the layer for the real values. If it is "restore is faster", time it. One check on the artifact is worth more than any number of passes reading the code that makes it.

Record both in `<dir>/signals.md` when they finish. A failure here is a finding, and so is a rig problem you had to fix to get a result (name it, so nobody reads it as the PR's).

## Step 4: Fan out specialized review passes

Spawn the following subagents **in parallel** (single message, multiple Agent tool calls). Use `subagent_type: code-reviewer`.

It is the only type that satisfies both constraints at once: read-only toward the repo by charter (it recommends fixes and never applies them), while still holding Write, so its findings land in `<dir>` instead of in the orchestrator's context. It is also built for reviewing a changeset rather than for search.

**Not `Explore`**, even though read-only is what you want: it has no Write, and Bash redirects and heredocs are blocked inside it too, so there is no route by which it can produce the artifact. Every pass then silently fails its output instruction and returns its findings as a final message — defeating the run directory, uniformly, across all passes at once. Explore also reads excerpts rather than whole files and describes itself as locating code rather than reviewing or auditing it.

**Not `general-purpose`**: it can write the artifact, but it can also edit the repo, and a review pass has no business holding that.

Restate the boundary in every pass prompt anyway, since the charter is a prompt and not a sandbox: the only file the agent may write is `<dir>/<pass-name>.md`, and it must not modify anything in the repo. Tell it not to run the test suite either, Step 3 already did that and its results are in `<dir>/signals.md`.

Each subagent prompt must include:
- Pointers to `<dir>/diff.patch`, `<dir>/intent.md`, `<dir>/conventions.md`, `<dir>/signals.md`
- The read-only boundary: write `<dir>/<pass-name>.md` and nothing else, modify no repo file, don't re-run the test suite
- Instruction to read full changed files (not just diff hunks) and chase callers/types/config when context is needed
- The specialized charter below
- Output instruction: write findings to `<dir>/<pass-name>.md`, one finding per line in the format `path:line — kind — severity — confidence — description — suggestion`.
  - **kind** is `issue`, `design`, or `style`:
    - `issue` — the code is broken, risky, or has a downside the author probably didn't intend (regardless of whether the line *looks* deliberately written). Bugs that look intentional are still issues. A convention violation that affects correctness or safety (e.g. "always parameterize queries", "always check this error") is an `issue`, not `style`. **Scope:** an issue must either (a) be on a line the diff actually adds/modifies, or (b) name a *specific causal link* to the diff — e.g. a new caller introduced by this PR now reaches a pre-existing weakness with attacker-controlled input. Pre-existing code that the diff merely sits next to (same file, nearby function, same module) is **out of scope**. If you notice something worth flagging in unchanged code, save it for "coverage notes" instead of issues.
    - `design` — the code does what the author intended, the choice is internally consistent, but the reviewer would have made a different one. Only raise where there's a concrete trade-off worth discussing — not matters of taste or naming preference. If `<dir>/conventions.md` documents the choice, divergence is `style` or `issue`, not `design`.
    - `style` — code style and idiom: naming, formatting, ordering, language idioms, comment/doc style, magic numbers, function length. Code works correctly and the author didn't make a meaningful design choice — it's just *how* the code is written. Prefer concrete references to the convention being violated (e.g. "CONTRIBUTING.md says snake_case for modules"). Don't flag style on lines the diff didn't touch.
    - When unsure between `issue` and `design`, prefer `issue`. When unsure between `design` and `style`, prefer `style`.
    - **Before filing anything as `issue`, check whether the author documented that exact choice.** A comment explaining the trade-off, an error message telling a human to clean up by hand, a header paragraph stating a limitation: all mean the author decided this on purpose, and it is `design` at most. Quote the line that shows they knew. This is the largest single source of noise in the merged set, because a deliberate choice reads identically to an oversight unless you go looking for the comment.
    - **Before filing anything that depends on how a third-party library behaves, read that library's source** at the version the repo pins, and at the latest release when the code may be tracking upstream. A code comment, a test comment or memory describing what the SDK does is a claim, not evidence. Download the package (`pip download`, `npm pack`, the wheel or crate from its registry) and cite the file and line. Without that citation the finding is `verify` at best.
  - **confidence** is `confident` (directly visible in the code being read) or `verify` (plausible but depends on assumptions about code/runtime not directly read). Default to `verify` when unsure — over-claiming confidence is the bigger failure mode. Style findings are almost always `confident`.
  - No prose, no recap, no preamble.
  - If the agent cannot write the file for any reason, it must say so explicitly and return the finding lines verbatim as its final message, nothing else. A silent failure to write looks identical to a pass that found nothing.
- Cap at ~15 findings per pass, with at most ~3 `design` and ~5 `style` of those

**Check the artifacts landed before moving on.** `ls <dir>/*.md` and confirm one file per pass. A pass whose file is missing has not run, however confident its final message sounded; write its returned lines to the file yourself before merging, and note in the final output that the pass reported through the transcript rather than to disk.

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

   **Severity is blast radius, not confidence.** How well a finding is evidenced changes how it is *written*, never how severe it is. A perfectly-reproduced defect sitting behind a blocker that already stops the code reaching it is Low, however clean the measurement. When a strong repro tempts you to promote something, that is the tell you are grading evidence instead of impact. Rank on what goes wrong and how often, then attach the evidence.
3. **Drop noise**: pure style nits unless they cause bugs. Also apply a **blast-radius filter** before keeping any finding at Medium or higher: in the realistic worst case for this codebase, does harm actually accumulate? A 1KB temp file in `/tmp/` that systemd-tmpfiles wipes, a leak on a path that's hit once per process lifetime, a race that the use case forecloses — all are technically real but practically zero. Drop them, or downgrade to Low if there's still a maintainability angle. The test: if you can't articulate concrete harm — "this fills the disk over N hours", "this corrupts user data on retry", "this fires on every request" — the severity is wrong.

   Also drop findings that name pre-existing code the diff didn't touch (see Step 4's `issue` scope rule). If a pass surfaced one, it leaked through; move it to coverage notes or omit.

   **Drop deliberate choices, however real.** If the author documented the behaviour (a comment stating the trade-off, an error message telling a human to intervene, a header paragraph naming the limitation), it is not an issue no matter how confidently a pass phrased it. Re-file as `design`, or drop. The passes are told to check this in Step 4; expect several to have missed it anyway, because a deliberate choice and an oversight look the same in a diff.

   Expect this step to remove most of what arrived. Roughly a third surviving to the presented set is healthy, and a merged list that keeps nearly everything means the filter did not run.
4. **Split by kind**: write `issue`-kind findings to `<dir>/issues.md`, `design`-kind to `<dir>/design.md`, and `style`-kind to `<dir>/style.md`. Issues drive verification, reproduction, and the main presentation. Design and style are separate output — neither is reproduced or verified. For design points, drop any item only one pass raised at low severity — almost always taste, not signal. For style, dedupe aggressively (the formatter pass and the dedicated style pass will overlap), and group near-duplicates into one entry where possible (e.g. "use snake_case for module names" with multiple file references rather than one entry per file).
5. **Intent check**: explicitly compare `<dir>/intent.md` against the diff. Does the diff actually do what the description claims? Are there changes in the diff *not* mentioned in the intent? Both directions matter — undisclosed scope creep is an `issue`.

   Then run every surviving finding against the **Deferred** and **Linked work** sections. A finding the author listed as deferred becomes a design question or is dropped. A finding about a gap that a linked PR closes is dropped, and so is one whose description of runtime behaviour contradicts what a linked PR's description states, until you have read the code that settles it.
6. **Verification checklist for High issues**: for each remaining High-severity issue (not design point), write a concrete verification step — the specific command, test case, manual check, or file/line to inspect that would confirm the issue is real. One per issue. These checks seed Step 6's reproduction for the High issues, and back the Step 7 checklist for any that Step 6 can't settle. Save to `<dir>/verify.md`.

## Step 6: Attempt to reproduce findings

For **every** `issue`-kind finding — all severities, not just High/Medium — try to actually produce evidence to confirm or refute it in practice before presenting. Design and style findings are not reproduced (they're trade-offs and presentation, not falsifiable claims). Spawn a single `subagent_type: general-purpose` agent for this step. Unlike the Step 4 passes it genuinely may need to touch the repo (a failing test, temporary instrumentation), which is why it gets the broader type and the explicit boundaries below.

The subagent prompt must include:
- Pointer to `<dir>/issues.md` (every issue-kind finding — attempt all of them) and `<dir>/verify.md` (the concrete pre-written checks for the High ones)
- Pointer to `<dir>/environments.md`, with the instruction that any finding needing root, x86_64, gVisor, docker, a cluster or live credentials is reproduced there, on the VM or cluster it names, using the recipe it gives. State in the prompt that the VM is running and usable. A subagent that isn't told this assumes the local box is all it has and marks the finding inconclusive.
- Instruction to attempt reproduction for each finding using the most appropriate technique:
  - **Run an existing test** that should fail given the bug.
  - **Write a tiny reproduction script in `<dir>/`** (never inside the repo) and run it — for parsing bugs, off-by-ones, edge cases.
  - **Run the linter/type checker scoped to specific files** if the finding is a static issue.
  - **Grep / read-cross-reference** to confirm structural claims (missing caller, asymmetric update, surviving old name).
  - **Mutate the code and run the tests** for a test-gap claim: change the line the finding says is unpinned (swap the key, drop the guard, delete the call), run the package's tests, and revert. A suite that still passes settles the claim in a way no reading can, and the mutation goes straight into the comment as evidence.
  - **Trace through code by hand** when no executable check is feasible — read the involved files end-to-end and write a 2-3 sentence justification.
- Repo modifications are allowed when reproduction genuinely requires them — adding a failing test inside the repo's test directory, instrumenting a function with temporary logging, generating a fixture, etc. Use this leeway when it actually helps, not by default.
- Boundaries that still apply:
  - **Snapshot before mutating.** Run `git status --porcelain` first. If the working tree is dirty (user has uncommitted changes), prefer creating *new* untracked files over modifying tracked ones, so cleanup is unambiguous. If the tree is clean, you have more room to modify and revert.
  - **Always clean up.** Before finishing, restore the working tree to its starting state. New files you created: delete them or move them to `<dir>/`. Tracked files you modified: `git checkout -- <file>`. Verify with `git status --porcelain` matching the snapshot.
  - **No history or remote mutations.** No `git commit`, `git push`, `git reset --hard`, `git rebase`, branch creation/deletion, or anything that touches `.git/` directly.
  - **No network side effects.** Tests and linters that hit the network as part of their normal operation are fine; explicit `curl`/`gh`/API calls to mutate external systems are not.
  - **No destructive shell commands** outside `/tmp/` (`rm -rf`, etc.).
- Record any repo-side artifacts created (and confirm cleanup) in the evidence column of `<dir>/reproduced.md`, e.g. `wrote tests/foo_repro_test.py, ran pytest, deleted file`.
- Time-box: ~3 minutes per finding. Attempt every issue; work highest-severity first so that if you run long, only the lowest-severity findings are left unattempted. Spend the time — running a real test or writing a real repro script is the whole point of this step.
- **`inconclusive` is a verdict you have to earn.** Before marking anything unreproducible, name the specific missing capability out loud and run the command that proves it is missing. The failure mode is reasoning from a true general fact to an untested specific one, and it is how a skill misses its own headline finding:
  - *The system under test can't run here* is not *this claim can't be tested here*. A change to a gVisor cycle on an arm64 box still contains arch-independent code whose semantics are testable in isolation. Pull the specific helper the finding is about and drive it directly.
  - *This needs the full pipeline* is usually false. Most findings reduce to one function, one parse, one ordering.
  - Prefer driving the branch's **own** helpers over reimplementing them, so a passing check says something about the code under review rather than about your copy of it.
  - Genuinely out of reach: prod-only configs, external services you cannot stand up, real concurrency at scale. Those are `inconclusive`, and say which one applies.
- **Check the framing, not just the claim.** A finding can be confirmed in every stated particular and still be wrong about what it means, usually because the pass missed a guard elsewhere that already handles the case. For each `confirmed`, read the surrounding path once more and ask what the author's code does about it. If the answer is "handles it two functions away", the correct verdict is `refuted`.
- Output: write `<dir>/reproduced.md` with one entry per finding: `path:line — [confirmed|refuted|inconclusive] — evidence (command run, test name, grep result, or reasoning)`.

After the subagent returns, read `<dir>/reproduced.md` and update the merged findings:
- **confirmed** findings: drop any `(verify)` tag, promote to `confident`. Confirming does not promote severity (Step 5).
- **refuted** findings: remove from the report entirely.
- **inconclusive** findings: keep, retain `(verify)` tag, note why reproduction wasn't feasible.

**Re-apply the severity rule now that the evidence exists.** Step 5 ranked findings before any of them had a reproduction. A vivid repro (a forged token signed with the real secret, a crash on a crafted input) is exactly what pulls a finding up the list after the fact. For each confirmed finding, restate its blast radius in one sentence, including who can reach it, on what path, for how long, and how often. Then rank on that sentence alone. "A manual build on a developer box, for about 75 seconds" is Low however clean the repro.

### Refute what survived

A confirmed finding means the mechanism happens. It does not mean the finding is right about what that mechanism means. In practice this is where most of the remaining errors are: a reproduction faithfully demonstrates something the author chose on purpose, that a linked PR is already fixing, that no real caller ever triggers, or that rests on a wrong belief about a dependency.

Spawn one fresh `subagent_type: code-reviewer` agent whose only job is to argue that each confirmed finding is the reviewer's misunderstanding. A fresh agent matters, because the one that reproduced a finding is anchored on it. Give it `<dir>/reproduced.md`, `<dir>/intent.md` (with its Deferred and Linked work sections) and the repo. It may write only `<dir>/refutation.md`, and may download dependency source into `<dir>`. For every confirmed finding it answers each of these with evidence, quoting a file and line or naming a command and its output:

1. **Did the author choose this?** Search the surrounding code, the commit messages and the PR description for a comment or sentence that explains it. Quote it if found.
2. **Is it deferred or already being fixed?** Check the Deferred list and read each linked PR's description and diff for the same gap.
3. **Does a real caller ever reach it?** Name the caller and the input it sends. A reproduction built on a synthetic input that no real client produces (a path the SDK never builds, a config no deployment sets) is not a defect in practice.
4. **Is the dependency claim true?** Read the library's source at the pinned version, and at the latest release if the code may be tracking upstream. Cite the file and line.
5. **Does the suggested fix conflict with the author's stated reason?** A fix that breaks the case the author documented is a sign the finding misread the design.

Output one line per finding: `path:line — [stands|reframe|refuted] — the evidence for that verdict`. Then apply it: drop `refuted`, move `reframe` to design notes as a question (quoting the line that shows the author knew), and keep `stands`. Expect this pass to cut a real share of the confirmed set. A refutation pass that cuts nothing probably did not read the linked PRs or the dependency source.

**Then look for another machine.** For anything still `inconclusive`, check `<dir>/environments.md` and the available skills for an environment that could settle it: the `x86-root-vm` VM, another architecture, a cluster, a container. A finding confirmed in the configuration the change actually targets is worth more than the rest of the report combined, and the environment usually exists. If an inconclusive verdict says "needs root/x86/runsc/the full stack", that is a routing miss from Step 2b, not a verdict. Run it there yourself.

Do not report a finding as unverifiable while an environment that could verify it sits unused.

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
- Mark anything `inconclusive` without having run the check that proves it is out of reach, or report a finding as unverifiable while an environment that could verify it sits unused.
- File a deliberate, documented choice as an `issue`.
- Let a strong reproduction raise a finding's severity.
- Trust that a pass ran because its final message sounded confident. Confirm its file exists.
- Present a confirmed finding that the refutation pass has not seen.
- Cite a third-party library's behaviour without having read its source at the pinned version.
- Leave the author's stated test plan, or the suites they say were not rerun, unrun while an environment that could run them sits idle.
- Record a check as skipped or not run because the local box lacks root, x86_64, runsc, an image or credentials. Route it to the environment Step 2b assigned, or ask for the missing input.
- Spawn a reproduction subagent without pointing it at `<dir>/environments.md` and telling it the VM is up.
