---
name: research
description: Investigate a question about the codebase (and optionally docs/web) read-only, then write a grounded research artifact with file:line references. Manual-only — invoke with `/research <question> [path]`. Use as the first step of the research→plan→implement loop, before /plan.
disable-model-invocation: true
argument-hint: "<question> [output path]"
allowed-tools: Read, Grep, Glob, Bash, Write, WebFetch, WebSearch, Agent
---

Investigate the question in `$ARGUMENTS` and write a **research artifact** — a
grounded, reviewable document about how the relevant code actually works. This
is the highest-leverage thing to review in the whole loop: a wrong line of
research can steer hundreds of lines of code wrong, so the goal is a document a
human can check in a few minutes. **Read-only: no plan, no code changes.**

## Method

1. **Decompose** the question into the specific things you need to learn.
2. **Isolate context with subagents.** Dispatch read-only `Explore` subagents
   (in parallel where the sub-questions are independent) to find, read, and
   summarize — so grep/read noise stays in *their* context and only conclusions
   return to yours. Subagents are for context isolation, not persona play; ask
   each for a tight conclusion with `file:line` references, not a dump.
3. **Ground every claim in the code.** Trace real definitions, callers, types,
   and config. Cite `path:line`. Never assert behavior you didn't read. If you
   consulted external docs, cite the URL.

## Output

Resolve the path from `$ARGUMENTS`; otherwise write to `thoughts/research/<slug>.md`
(create `thoughts/` if absent), or an existing `plans/`/`docs/`/`specs/` dir if
the repo already uses one. Sections:

- **Question** — what this investigates and why.
- **Summary** — the answer in a few sentences.
- **How it works** — the mechanism, with `path:line` anchors throughout.
- **Key files** — the files that matter, each with a one-line role.
- **Constraints & gotchas** — invariants, edge cases, footguns, prior decisions.
- **Patterns to follow** — existing conventions any change here must match.
- **Open questions** — what's still unknown or needs a human decision.

Keep it tight and skimmable — anchors over prose.

## Notes

- Don't propose a plan or write code — that's `/plan` and `/implement`.
- End by suggesting `/plan <task>` using this research file as input.
- Suggest gitignoring `thoughts/` if the user wants these notes personal.
