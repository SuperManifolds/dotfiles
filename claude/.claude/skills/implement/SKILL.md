---
name: implement
description: Execute an existing plan or spec file task-by-task, verifying each step with the project's tests and checking it off, pausing at checkpoints for review. Use when asked to implement, execute, or work through a plan or spec file that already exists, and as the last step of the research→plan→implement loop after /plan.
argument-hint: "<plan or spec file> [task range]"
allowed-tools: Read, Grep, Glob, Bash, Edit, Write, TodoWrite
---

Execute the plan/spec file named in `$ARGUMENTS` (a `- [ ]` task checklist, e.g.
from `/plan`). If a task range is given, do only those. Work the plan
faithfully and verifiably — don't improvise around it.

## Loop

1. **Read the plan** and load its task checklist into a TodoWrite list.
2. **One task at a time.** For each task:
   - Make the **minimal** change that satisfies it (surgical — touch only what
     the task requires; match existing style).
   - **Verify it** with the task's stated check — run the project's real
     tests/build/lint, scoped to what changed. Show the evidence.
   - On success, tick the box to `- [x]` in the plan file so progress survives
     a context reset. On failure, fix it before moving on.
3. **Compact between phases.** After a logical group of tasks, write a short
   progress note into the plan file and suggest `/compact` — frequent intentional
   compaction keeps long, multi-session work coherent (aim to stay well under a
   full context window, not to fill it).
4. **Stop at checkpoints for review.** Pause at the end of each logical group,
   and *before* anything destructive or hard to reverse. Don't run the whole
   plan unattended.

## Stop and report — don't push through — when:

- A task can't be verified, or its check fails in a way the plan didn't anticipate.
- The plan is wrong or missing a step (reality diverged from the plan). Surface
  it and propose a plan fix rather than coding around it.
- A task would need a new dependency, a secret, or a destructive action.

## Respect the global rules

Surgical changes; never add dependencies without asking; run build/test/lint and
show evidence rather than asserting; conventional commits only when asked (use
`/commit`). Don't `git push` or open PRs unless asked.
