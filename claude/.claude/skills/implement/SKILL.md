---
name: implement
description: Execute an existing plan or spec file task-by-task, verifying each step with the project's tests and checking it off, pausing at checkpoints for review. Use when asked to implement, execute, or work through a plan or spec file that already exists, and as the last step of the research→plan→implement loop after /plan.
argument-hint: "<plan or spec file> [task range] [--through <phase> | --all] [--commit]"
allowed-tools: Read, Grep, Glob, Bash, Edit, Write, TaskCreate, TaskUpdate, TaskList, Skill
---

Execute the plan/spec file named in `$ARGUMENTS` (a `- [ ]` task checklist, e.g.
from `/plan`). If a task range is given, do only those. Work the plan
faithfully and verifiably; don't improvise around it.

## Options

- `--through <phase>`: run every phase up to and including `<phase>` (its
  number or heading) without pausing between them, then stop for review.
- `--all`: run every remaining phase without pausing between them.
- `--commit`: after each phase passes its checks, commit that phase's changes
  with the `/commit` skill (this flag is the explicit request that skill needs).
  Pass it a hint naming the phase and the files the phase touched, so unrelated
  working-tree changes stay out of the commit.

Without `--through` or `--all`, pause at the end of each phase. "Continue" or
"keep going" from the user means: run the next phase, keeping the same
`--commit` setting.

## Loop

1. **Read the plan** and load its task checklist into the task list
   (TaskCreate/TaskUpdate).
2. **One task at a time.** For each task:
   - Make the **minimal** change that satisfies it (surgical: touch only what
     the task requires; match existing style).
   - **Verify it** with the task's stated check: run the project's real
     tests/build/lint, scoped to what changed. Show the evidence.
   - On success, tick the box to `- [x]` in the plan file so progress survives
     a context reset. On failure, fix it before moving on.
3. **End of each phase:** write a one-line progress note into the plan file
   (what's done, what's next), commit if `--commit` is set, then either pause
   for review or, under `--through`/`--all`, start the next phase.

## Stop and report, don't push through, when:

These apply under `--through` and `--all` too.

- A task can't be verified, or its check fails in a way the plan didn't anticipate.
- The plan is wrong or missing a step (reality diverged from the plan). Surface
  it and propose a plan fix rather than coding around it.
- A task would need a new dependency, a secret, or a destructive or
  hard-to-reverse action. Ask before doing it.

## Respect the global rules

Surgical changes; never add dependencies without asking; run build/test/lint and
show evidence rather than asserting; commit only under `--commit` or when asked
(always via `/commit`). Don't `git push` or open PRs unless asked.
