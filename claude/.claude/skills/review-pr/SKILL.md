---
name: review-pr
description: Review the current branch as a pull request, comparing against the base branch. Use when the user asks to review a PR, do a code review, or review changes.
argument-hint: "[base-branch (default: main)]"
disable-model-invocation: true
allowed-tools: Bash(git *), Bash(gh *), Bash(ls *), Read, Glob, Grep
---

Review the current branch against the base branch. The base branch is $ARGUMENTS if provided, otherwise `main`.

## Step 1: Understand the changeset

Run these in parallel:
- `git log --oneline <base>..HEAD` to see commits
- `git diff --stat <base>...HEAD` to see changed files
- `git diff <base>...HEAD` and save the output path for reference

## Step 2: Categorize changed files into review areas

From the diff stat, group files by priority:
1. Core library/source code (highest priority)
2. Tests and test infrastructure
3. CI/CD workflows
4. Dockerfiles and deployment configs
5. Documentation and READMEs
6. Build scripts, configs, and tooling

## Step 3: Read and review each area

Read the changed files. Focus on finding:

### High severity
- Memory safety issues (use-after-free, buffer overflows, uninitialized memory)
- Unsafe code correctness (raw pointers, FFI boundary issues like panic-across-FFI)
- Security vulnerabilities (injection, hardcoded secrets, insecure defaults)
- Data races and concurrency bugs (missing synchronization, deadlock potential)
- Error handling that silently drops failures in critical paths

### Medium severity
- Logic errors and off-by-one mistakes
- Resource leaks (file handles, connections, memory)
- API misuse or contract violations
- Inconsistencies within the PR (e.g., mixed dependency versions in CI)
- Missing validation at system boundaries

### Low severity
- Performance concerns (unnecessary copies, N+1 patterns)
- Code quality (dead code, misleading names, missing comments on non-obvious invariants)
- Typos in code identifiers or user-facing strings

## Step 4: Present the review

Structure output as:

1. **One-line summary** of what the changes do
2. **Findings grouped by severity** (High / Medium / Low)
   - Each finding: file path with line number, what the issue is, concrete suggestion
   - Use format `path/to/file.rs:123`
3. **Positive notes** — briefly call out things done well

Do NOT:
- Summarize what every file does
- Flag style preferences or nitpicks unless they cause bugs
- Suggest adding docs/comments to unchanged code
- Recommend refactors unrelated to the changes
