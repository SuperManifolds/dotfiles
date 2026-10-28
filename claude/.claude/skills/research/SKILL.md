---
name: research
description: Investigate a question about the codebase (and optionally docs/web) read-only, then write a grounded research artifact with file:line references. Use when asked to research, investigate, trace, or understand how something works before changing it, and as the first step of the research→plan→implement loop before /plan.
argument-hint: "<question> [output path]"
model: fable
allowed-tools: Read, Grep, Glob, Bash, Write, WebFetch, WebSearch, Agent, Workflow, AskUserQuestion
---

Investigate the question in `$ARGUMENTS` and write a **research artifact** — a
grounded, reviewable document about how the relevant code actually works. This
is the highest-leverage thing to review in the whole loop: a wrong line of
research can steer hundreds of lines of code wrong, so the goal is a document a
human can check in a few minutes. **Read-only: no plan, no code changes.**

This skill runs on Fable (frontmatter `model: fable`): you decompose, brief,
check and synthesize. Opus `researcher` subagents do the reading.

## Method

1. **Decompose** the question into the specific sub-questions you need answered.
   Scale the count to the question: one researcher for a single mechanism, two
   to four for a comparison or a feature that crosses modules, more only when
   the subsystems are genuinely independent.
2. **Brief each researcher.** Spawn `subagent_type: researcher` agents in
   parallel, one per sub-question, and pass `model: opus` on every call so none
   inherits Fable. Each brief has four parts, because a vague brief is how
   researchers duplicate work or leave gaps:
   - **Objective:** the sub-question and why it matters to the main question.
   - **Output:** the notes file `thoughts/research/<slug>/<sub-question>.md` and
     what it must contain.
   - **Sources:** the directories, files, docs or pinned dependency sources to
     use, including where the language's standard library lives at the pinned
     version when the question touches it.
   - **Boundaries:** what is out of scope, so researchers don't overlap.

   More than about six researchers: run them as a Workflow instead of separate
   Agent calls (this skill is your opt-in), with `agentType: 'researcher'`,
   `model: 'opus'` and `effort: 'xhigh'` on every `agent()` call.
3. **Check before you synthesize.** Read each notes file. For every claim the
   answer depends on, open the cited `path:line` yourself and confirm it says
   what the researcher says. Where two researchers disagree or a claim has no
   anchor, resolve it by reading the code or send a targeted follow-up; never
   smooth it over.
4. **Ground every claim in the code.** Cite `path:line`. Never assert behavior
   nobody read. Claims about a library or standard library cite its source at
   the pinned version, not memory. If you consulted external docs, cite the URL.

## Output

Resolve the path from `$ARGUMENTS`; otherwise write to `thoughts/research/<slug>.md`
(create `thoughts/` if absent), or an existing `plans/`/`docs/`/`specs/` dir if
the repo already uses one. The researchers' notes stay beside it in
`thoughts/research/<slug>/`. Sections:

- **Question** — what this investigates and why.
- **Summary** — the answer in a few sentences.
- **How it works** — the mechanism, with `path:line` anchors throughout.
- **Key files** — the files that matter, each with a one-line role.
- **Constraints & gotchas** — invariants, edge cases, footguns, prior decisions.
- **Patterns to follow** — existing conventions any change here must match.
- **Open questions** — what's still unknown or needs a human decision.

Keep it tight and skimmable — anchors over prose.

## Decisions

Open questions that need a human decision are asked, not just listed. After
writing the file and giving the summary, walk the user through them with
`AskUserQuestion` instead of leaving them as prose in chat:

- Ask only what changes the plan. Things you can settle by reading code, or that
  have an obvious default, become recorded assumptions, not questions.
- Up to 4 questions per call, in batches until the decisions are covered. Later
  batches can build on earlier answers.
- Give 2–4 concrete options each. Put your recommendation first, with
  "(Recommended)" in its label. Each description says what happens if it is
  chosen and what it costs, in plain words.
- You may recommend, but never close a question yourself. A question stays open
  until the user answers it.
- Record the answers in the research file under `## Decisions (<date>)`, and cut
  `## Open questions` down to what is still open.

If `AskUserQuestion` is not available, or the session is not interactive, leave
the questions in `## Open questions` and say so.

## Notes

- Don't propose a plan or write code — that's `/plan` and `/implement`.
- End by suggesting `/plan <task>` using this research file as input, once the
  decisions are recorded.
- Suggest gitignoring `thoughts/` if the user wants these notes personal.
