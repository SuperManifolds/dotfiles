---
name: commit
description: Split the working changes into well-formed conventional commits following the user's git conventions. Manual-only — invoke with `/commit [hint]`.
disable-model-invocation: true
argument-hint: "[optional focus or subject hint]"
allowed-tools: Bash(git *), Read, Grep, Glob
---

Create one or more commits from the current working changes. `$ARGUMENTS`, if
given, is a hint about the subject or which changes to focus on.

Assume the changes are already verified (build/test/lint) unless the diff
obviously warrants a check — this skill is about committing well, not testing.

## Steps

1. **Survey the state** (run in parallel):
   - `git status --short`
   - `git diff` and `git diff --staged` — the actual changes
   - `git log --oneline -10` — to match this repo's subject style and scope
     vocabulary (see step 3)
   - `git branch --show-current` — note if on the default branch

2. **Group into logical commits.** Do not lump unrelated changes together. One
   commit = one coherent change. If the working tree mixes concerns (e.g. a
   feature edit plus an unrelated config tweak), make separate commits and stage
   each explicitly with `git add <paths>` — never blanket `git add -A`. Order
   commits so each leaves the tree in a working state.

3. **Write each message** in the repo's convention:
   - Conventional-commit type (`feat`, `fix`, `chore`, `docs`, `refactor`,
     `test`, `perf`, `build`, `ci`). Add a **scope** when the repo uses one —
     infer the vocabulary from recent `git log` (e.g. `fix(networking):`).
   - Short imperative subject, lower-case, no trailing period, ~50 chars.
   - A body only when the *why* isn't obvious from the subject + diff. Wrap at
     ~72 cols. Explain intent/trade-offs, not a file-by-file recap.
   - **Never** add AI/Claude Code attribution or co-author trailers.

4. **Commit.** Stage the specific paths for each group, then commit. The global
   gitleaks pre-commit hook will block secrets — if it fires, stop and surface
   it rather than using `--no-verify`.

5. **Report** the resulting `git log --oneline` for the new commits.

## Guardrails

- **Never** `git commit --amend` on a commit that's already pushed, and don't
  rewrite published history.
- Don't `git push` — that's a separate, explicit step.
- If the working tree is clean, say so and stop.
- If a change looks like it shouldn't be committed (secret, large binary,
  vendored dir, debug leftover, `.env`), flag it and ask before staging.
- If on the default branch (`main`/`master`) and this looks like feature work,
  mention that a branch may be wanted — but still commit if the user asked.
