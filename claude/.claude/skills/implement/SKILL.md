---
name: implement
description: Execute an existing plan or spec file phase by phase through fresh implementer subagents, verifying each phase with the project's tests, then review the result with /review-pr and fix the findings the user picks. Use when asked to implement, execute, or work through a plan or spec file that already exists, and as the last step of the research→plan→implement loop after /plan.
argument-hint: "<plan or spec file> [task range] [--through <phase> | --all] [--commit] [--no-review]"
allowed-tools: Read, Grep, Glob, Bash, Edit, Write, TaskCreate, TaskUpdate, TaskList, Skill, Agent, SendMessage, AskUserQuestion
---

Execute the plan/spec file named in `$ARGUMENTS` (phases with `- [ ]` task
checklists, e.g. from `/plan`). If a task range is given, do only those. Work
the plan faithfully and verifiably; don't improvise around it.

You orchestrate; you don't write the code. Each phase goes to a fresh
`implementer` subagent (Opus at xhigh, consulting the Fable advisor at decision
points), and you verify what comes back. The session's own model, with the
Fable advisor, runs this loop.

## Options

- `--through <phase>`: run every phase up to and including `<phase>` (its
  number or heading) without pausing between them, then stop for review.
- `--all`: run every remaining phase without pausing between them.
- `--commit`: after each phase passes its checks, commit that phase's changes
  with the `/commit` skill (this flag is the explicit request that skill needs).
  Pass it a hint naming the phase and the files the phase touched, so unrelated
  working-tree changes stay out of the commit.
- `--no-review`: skip the review step at the end.

Without `--through` or `--all`, pause at the end of each phase. "Continue" or
"keep going" from the user means: run the next phase, keeping the same
`--commit` setting.

## Setup

1. **Read the plan** and load its phases into the task list
   (TaskCreate/TaskUpdate).
2. **Record the base.** Note `git rev-parse HEAD` and `git status --porcelain`
   in the plan's Progress ledger as the run's starting point. The review at the
   end diffs against it.
3. **Make a run directory** beside the plan, `thoughts/plans/<slug>.runs/`, for
   implementer reports.

## Loop: one phase at a time

1. **Brief a fresh implementer.** Spawn `subagent_type: implementer` with
   `model: opus`. Never resume the previous phase's implementer for a new
   phase: a fresh context per phase, with a complete brief, loses less than a
   long one. The brief is everything it gets, so it carries:
   - the phase's tasks and done-condition checks, copied from the plan, with
     where each check runs (and, for VM checks, the `x86-root-vm` recipe);
   - the plan's Goal, the constraints and rejected approaches that apply, and
     the decisions recorded in the plan;
   - the Progress ledger and `git log --oneline <base>..HEAD`, so it knows what
     earlier phases did;
   - the report file, `thoughts/plans/<slug>.runs/phase-<n>.md`;
   - the rules: no commits, no subagents, no new dependencies, stop with
     `BLOCKED` or `NEEDS_CONTEXT` rather than working around the plan.
2. **Check which model ran.** Subagents have silently fallen back to another
   model before. Grep the agent's transcript (the output file the Agent result
   names) for `"model":` and confirm it ran on the model you asked for. If not,
   stop and tell the user.
3. **Verify it yourself.** Don't take the report's word. Rerun the phase's check
   commands yourself, in their assigned environments, and read the phase's diff
   (`git diff` against the state before the phase). Confirm the diff does what
   the tasks say and nothing outside them.
4. **On success**, tick the phase's boxes to `- [x]`, append a line to the
   Progress ledger (status, commit if any, notes), commit if `--commit` is set,
   then pause for review or, under `--through`/`--all`, start the next phase.
5. **On failure**, escalate in this order, at most two retries per phase:
   1. **Retry with a diagnosis.** Write down what failed and why (the test
      output plus your reading of the cause) and send it to the same
      implementer with `SendMessage`.
   2. **Escalate to Fable, fresh.** Spawn a new `implementer` with
      `model: fable`, briefed as in step 1 plus your diagnosis of both failed
      attempts. Leave the edits on disk; don't pass the failed agent's
      transcript, which costs more and recovers less than a fresh brief.
   3. **Ask the user** with `AskUserQuestion`: what failed, what each attempt
      tried, and 2–4 options (your recommendation first, marked
      "(Recommended)").

**After a compaction or a resumed session,** rebuild your state from the plan's
Progress ledger and `git log`, not from memory, before dispatching anything.
Re-dispatching a finished phase is the most expensive mistake this loop makes.

## Stop and ask, don't push through, when:

These apply under `--through` and `--all` too. Each stop is an
`AskUserQuestion` with concrete options and your recommendation first, not a
prose report:

- A phase can't be verified, or its check fails in a way the plan didn't anticipate.
- An implementer reports `BLOCKED` or `NEEDS_CONTEXT`, or the plan is wrong or
  missing a step (reality diverged from the plan). Offer a plan fix as one of
  the options rather than coding around it.
- A task would need a new dependency, a secret, or a destructive or
  hard-to-reverse action.

## Review and fix

Once every phase is done (and unless `--no-review` is set):

1. **Run `/review-pr`** with the Skill tool, passing the run's base commit and
   `--plan <plan path>`, so the review checks the diff against the plan's
   done-conditions and treats the plan's decisions as deliberate.
2. **Let the user pick the fixes.** Put every surviving issue to the user with
   `AskUserQuestion`, multi-select, up to 4 findings per question and 4
   questions per call, in batches. Each option is one finding: severity,
   `path:line` and the problem in the label or description, and mark the ones
   you recommend fixing with "(Recommended)". Never fix a finding the user
   didn't pick.
3. **Fix as a new phase.** Append a "Review fixes" phase to the plan with the
   picked findings as tasks, and run it through the loop above.
4. **Re-review only the fix diff** with `/review-pr <commit before the fix
   phase> --plan <plan path> --fix-diff`, then repeat steps 2–4 for new
   findings. Stop after two fix rounds and report what is still open.

## Respect the global rules

Surgical changes; never add dependencies without asking; run build/test/lint and
show evidence rather than asserting; commit only under `--commit` or when asked
(always via `/commit`). Don't `git push` or open PRs unless asked.
