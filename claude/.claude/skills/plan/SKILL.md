---
name: plan
description: Turn a task (optionally grounded by a /research artifact) into a self-contained implementation spec written to a file, so the work survives context resets and can be executed in a fresh session. Use when asked to plan, spec out, or design the approach for a change, and as the middle step of the research→plan→implement loop before /implement.
argument-hint: "<task description> [output path (default: ./spec.md)]"
model: fable
allowed-tools: Read, Grep, Glob, Bash, Write, WebFetch, WebSearch, Agent, AskUserQuestion, Artifact, Skill
---

Produce an implementation plan for the task in `$ARGUMENTS` and write it to a
file. This is planning only — **do not implement**. The output is a spec a
fresh session (or a subagent) can execute without the context you have now.

This skill runs on Fable (frontmatter `model: fable`): you make the design
calls and write the plan. Opus `researcher` subagents gather grounding, and the
Fable `oracle` critiques the plan before the user sees it.

Resolve the output path from `$ARGUMENTS` if a path is given; otherwise write to
`thoughts/plans/<slug>.md` (matching `/research`), or an existing `plans/`,
`docs/`, or `specs/` directory if the repo already uses one, else `./spec.md`.
If the file exists, read it and update rather than clobber.

If a research artifact exists (a `/research` output in `thoughts/research/`, or
one named in `$ARGUMENTS`), read it and its notes directory first and build the
plan on top of it rather than re-investigating from scratch.

## Steps

1. **Pin the goal.** State the concrete outcome and its done-condition. If a
   key spec is genuinely missing and it blocks correctness, ask 1–2 focused
   questions first with `AskUserQuestion` — otherwise proceed on reasonable
   assumptions and record them. Decisions already recorded in the research
   artifact are settled; don't ask them again.

2. **Ground it in the codebase.** Find the files that will change, the existing
   patterns to follow, the test setup, and the exact build/test/lint commands
   (from CLAUDE.md, Makefile, package.json, Cargo, build.zig, …), and where each
   check has to run (root, x86_64 or gVisor checks run on the `x86-root-vm`
   VM). Delegate the reading to `subagent_type: researcher` agents with
   `model: opus` on every call, briefed as `/research` does (objective, output
   file under `thoughts/plans/<slug>/`, sources, boundaries). Don't guess where
   things live: have it looked up, and open the anchors you rely on yourself.

3. **Write the spec** to the resolved path with these sections:
   - **Goal** — one paragraph: what and why, and the done-condition.
   - **Context** — key files (`path:line` where useful), constraints,
     conventions, gotchas, assumptions made.
   - **Approach** — the chosen strategy in a few sentences; note alternatives
     rejected and why, if the choice is non-obvious.
   - **Phases**: ordered phases, each written as a standalone brief, because
     `/implement` hands each one to a fresh implementer that sees nothing else:
     - the tasks, as `- [ ]` boxes, each small and independently verifiable;
     - the files it touches;
     - the constraints and the approaches already rejected that apply to it;
     - its done-condition, as exact check commands and where each runs.
   - **Verification** — the exact commands that prove the whole thing works.
   - **Progress**: an empty ledger `/implement` appends to (one line per phase:
     status, commit, notes).
   - **Open questions** — anything unresolved that needs a decision.

   Write for a reader with zero prior context. Prefer concrete file/command
   references over prose. No "TBD": a section you can't fill is an open
   question. Keep it tight: a plan, not an essay.

4. **Have the oracle critique it.** Spawn `subagent_type: oracle` (it runs on
   Fable) with the spec path and any research artifact. Ask for: wrong or
   risky assumptions, missing phases or steps, any "TBD" or vague task, phases
   whose briefs depend on context they don't carry, checks that don't actually
   prove the done-condition, and simpler alternatives. Fix what holds up; what
   needs a human call becomes an open question. Record in the spec what the
   critique changed.

5. **Settle the open questions.** If the spec ends with open questions that need
   a human decision, walk the user through them with `AskUserQuestion` instead
   of listing them in chat:
   - Up to 4 questions per call, in batches. 2–4 concrete options each, with
     your recommendation first and "(Recommended)" in its label. Each
     description says what happens if it is chosen and what it costs.
   - You may recommend, but never close a question yourself. A question stays
     open until the user answers it.
   - Record the answers in the spec under `## Decisions (<date>)`, update any
     task they change, and cut `## Open questions` down to what is still open
     ("None." when nothing is).
   - Assumptions you made stay in **Context** as assumptions; ask only about the
     ones that change the plan.

   If `AskUserQuestion` is not available, or the session is not interactive,
   leave the questions in the spec and say so.

6. **Publish a digest.** Once the questions are settled, build an HTML page of
   the plan and publish it with the `Artifact` tool, so the plan can be read in
   a few minutes. Follow the tool's own flow (quickstart or the `artifact-design`
   skill first; write the page to the scratchpad; publish). The page is a
   digest, not a transcription of the Markdown:
   - no narrative prose: short labels, pairs, tables and lists;
   - done-conditions as a checklist;
   - decisions as label and answer pairs;
   - any registry-like data (settings, endpoints, files) as one table, with a
     filter when it has more than about 15 rows;
   - phases, each with a one-line summary and its check, with detail collapsed;
   - assumptions to confirm, and the verification commands.

   Use the project's own colours and fonts when it has them. The spec file stays
   the source of truth; say that the page is a snapshot. Skip this step if the
   `Artifact` tool is not available, or the user asked for the file only.

7. **Report** the spec path, the artifact link, and a one-line summary. Suggest
   reviewing the plan before coding — a wrong line here costs far more than a
   wrong line of code — then `/implement <path>` (ideally in a fresh session) to
   execute it.

## Notes

- Persisting the plan to a file is the point: it's the memory that lets long or
  multi-session work stay coherent across context resets. Update the checklist
  as tasks complete.
- Don't create branches, commit, or edit source files — this skill only writes
  the spec file and publishes its digest page.
