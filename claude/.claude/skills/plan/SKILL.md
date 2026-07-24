---
name: plan
description: Turn a task (optionally grounded by a /research artifact) into a self-contained implementation spec written to a file, so the work survives context resets and can be executed in a fresh session. Manual-only — invoke with `/plan <task> [path]`. Use as the middle step of the research→plan→implement loop, before /implement.
disable-model-invocation: true
argument-hint: "<task description> [output path (default: ./spec.md)]"
allowed-tools: Read, Grep, Glob, Bash, Write, WebFetch, WebSearch
---

Produce an implementation plan for the task in `$ARGUMENTS` and write it to a
file. This is planning only — **do not implement**. The output is a spec a
fresh session (or a subagent) can execute without the context you have now.

Resolve the output path from `$ARGUMENTS` if a path is given; otherwise write to
`thoughts/plans/<slug>.md` (matching `/research`), or an existing `plans/`,
`docs/`, or `specs/` directory if the repo already uses one, else `./spec.md`.
If the file exists, read it and update rather than clobber.

If a research artifact exists (a `/research` output in `thoughts/research/`, or
one named in `$ARGUMENTS`), read it first and build the plan on top of it rather
than re-investigating from scratch.

## Steps

1. **Pin the goal.** State the concrete outcome and its done-condition. If a
   key spec is genuinely missing and it blocks correctness, ask 1–2 focused
   questions first — otherwise proceed on reasonable assumptions and record them.

2. **Ground it in the codebase.** Read-only exploration: find the files that
   will change, the existing patterns to follow, the test setup, and the exact
   build/test/lint commands (from CLAUDE.md, Makefile, package.json, Cargo, …).
   Don't guess where things live — look.

3. **Write the spec** to the resolved path with these sections:
   - **Goal** — one paragraph: what and why, and the done-condition.
   - **Context** — key files (`path:line` where useful), constraints,
     conventions, gotchas, assumptions made.
   - **Approach** — the chosen strategy in a few sentences; note alternatives
     rejected and why, if the choice is non-obvious.
   - **Tasks** — an ordered checklist. Each task is small, independently
     verifiable, and names a concrete check (a command to run, a test to add,
     a behavior to observe). Use `- [ ]` boxes.
   - **Verification** — the exact commands that prove the whole thing works.
   - **Open questions** — anything unresolved that needs a decision.

   Write for a reader with zero prior context. Prefer concrete file/command
   references over prose. Keep it tight — a plan, not an essay.

4. **Report** the path and a one-line summary. Suggest reviewing the plan before
   coding — a wrong line here costs far more than a wrong line of code — then
   `/implement <path>` (ideally in a fresh session) to execute it.

## Notes

- Persisting the plan to a file is the point: it's the memory that lets long or
  multi-session work stay coherent across context resets. Update the checklist
  as tasks complete.
- Don't create branches, commit, or edit source files — this skill only writes
  the spec file.
