---
name: review-comments
description: Turn review findings that already exist into a posted PR review, filtering hard, labelling blocker/nit/flag, drafting in the reviewer's own voice, gating on their approval, then posting. Use when asked to draft or post review comments on a PR. Needs findings first, from /review-pr or a manual read, and never posts without explicit sign-off.
argument-hint: "[pr-number (default: PR for current branch)]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Take findings that already exist (from `/review-pr`, from this conversation, or from a manual read)
and turn them into a posted review on `$ARGUMENTS` (or the PR for the current branch, via
`gh pr view --json number --jq .number`).

This skill does **not** find bugs. If there are no findings yet, run `/review-pr` first.

The pipeline is: read the authority → verify → filter → classify → draft → **the reviewer approves**
→ post. The approval gate is not ceremony; it is what makes the comments legitimate.

Throughout, `REPO` and `ME` are resolved from the environment rather than hardcoded:

```
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
ME=$(gh api user --jq .login)
```

## Step 0: Read the team's review policy, do not work from memory

If the repo documents its review process, that document is the authority, not this skill and not
anything remembered about it. Find it first:

```
ls rfd/ 2>/dev/null | grep -i review        # or: fd -i 'review' docs/ rfd/ CONTRIBUTING.md
```

**Read the passage on AI-assisted review before acting on it.** Paraphrases have been wrong before
in ways that changed what got done: a stored summary once recorded the AI-posting rule as an
unconditional ban when the document says something narrower.

The rule as it actually reads, in this repo's case, and the reason this skill is shaped the way it
is: the test is whether **a person chose** the comment, not who executed the API call. A finding a
reviewer filtered and decided to post, or a reply drafted with AI, still counts as that reviewer's
comment. What the policy forbids is unattended tooling posting raw, unfiltered output. Confirm that
against the source rather than trusting this summary.

Two things stay unconditional regardless:
- **Never select APPROVE on the reviewer's behalf.** An approval is personal accountability for the
  change. Post `event: "COMMENT"` and hand back the verdict command.
- **Never post without sign-off on the drafts** (Step 5). The skill's own iteration is not approval.

Also load the numbered principles if the document has them. The ones that change the output:
verify rather than read, read the system not just the diff, AI surfaces candidates and a human
decides, label every comment, keep the count down, unblock now and capture the rest as tracker
issues, name the author and praise something concrete.

## Step 1: Calibrate the voice against the real corpus

Do this every time. Do not trust a cached description of anyone's style, including the one below.

```
gh api "/repos/$REPO/pulls/comments?per_page=100&sort=created&direction=desc" \
  --jq ".[] | select(.user.login==\"$ME\") | .body"
```

Read 15-20 of them and match what you see. The pattern to expect, as a starting point to confirm or
correct against the fetch:

- Label, then straight into the finding. **No praise sentence in inline comments at all.**
- First person, own testing, stated flatly. The shape is a claim then the measurement that settles
  it, often with a colon. Both examples below are illustrative, not real comments.
  `blocker: this map can't be preallocated, I tried it and the setup call returns EINVAL` /
  `I pushed 500 requests through and read the counter back: still 0`.
- Contractions throughout. Bare numbers, no units prose: `262144`, `58MB`, `17-CPU`.
- Casual hedges and closes: `Cheapest fix is probably…`, `Probably worth a tracker issue.`
- Direct questions to the author: `Does this need to be that big?`
- Length tracks evidence volume, not a target. Simple notes run ~120 chars; a comment carrying a
  real measurement runs 350-450 and that is correct. Treat the short end as a floor, never a cap.

Forbidden, all of these have been rejected in review:
- Em dashes. Use a comma or a full stop.
- Superlative-plus-rationale scaffolding (`the best part of this PR is X, which is the right
  instinct`), performative hedges (`the call I'd want someone to make`), triads.
- Headers, bullets or tables **inside** an inline comment. Prose only.
- `Suggestion:` as a separate line. Fold it into the same sentence.
- Formal connectors. `log and carry on` not `log and continue`; `isn't there` not `is not there`.

When the reviewer supplies their own wording for something, use it verbatim and do not improve it.
Openers are where drafts get rejected most often; expect two or three passes on the first sentence
alone and do not treat that as failure.

## Step 2: Verify before you write

An approval that never ran the code is the gap a review policy exists to close. Before drafting:
pull the branch, run the project's real lint/build/test (per its `AGENTS.md` or equivalent), and
capture exact commands and results. Note explicitly what you did **not** run.

For any finding you intend to post, prefer a reproduction over a code-reading argument. A
two-command repro moves a comment from arguable to settled, and it is what good comments look like.
If a finding cannot be reproduced locally, say so in the comment or drop it.

Do not post a finding that contradicts a comment the author wrote deliberately. Before calling
something a defect, check whether the author documented that exact choice. If they did, it is a
design disagreement: put it in the body as a question, or leave it out.

Beware of verifying with the wrong instrument. A check that reads the wrong file, or a shape test
where a real parse was needed, produces a false pass that reads exactly like a real one.

## Step 3: Filter hard

This is the step that gets skipped and it is the most important one. One high-signal finding beats
twenty plausible ones, and a review with twenty comments is a smell rather than thoroughness.

From the candidate set, keep only what a person should spend attention on. Target shape:

- **0-2 blockers.** Dangerous, incomplete or broken. Label `blocker:`.
- **2-5 flags.** Worth knowing, author decides. Label `flag:`.
- **2-4 nits.** Small, take or leave. Label `nit:`.
- **Everything else → the issue tracker** (Step 7), not a PR comment.

Drop, do not post: findings on pre-existing code the diff only sits beside, style preferences that
cause no bug, missing tests and missing docs (tracker items), and anything where the realistic
worst case has no concrete harm.

Fold near-duplicates into one comment with several line references rather than one comment each.

## Step 4: Draft

**Body.** Longer than an inline comment is fine. Structure that has worked:

1. One short sentence of concrete praise, naming the author. Inline comments carry no praise, so
   this is the only place it goes.
2. The blocker in two or three sentences, with the repro, ending `Details inline.`
3. What you verified, as a flat list of commands and results, plus what you did not run.
4. Anything worth knowing that is not a comment (e.g. a test cell that gives some path no
   coverage), and where it is going instead.

**Inline comments.** One per finding: `<label>: <observation>, <evidence>, <fix folded in>`. Lead
with the observation, no preamble, no narration of how you verified beyond the evidence itself.

## Step 5: Human review gate

Present the body and every comment **in the conversation**, as quoted blocks readable without
opening a file. Do not post yet.

Then wait. Post only on an explicit instruction to post. If the drafts have not been read, there is
no instruction that authorises posting.

## Step 6: Post

Resolve anchors first. **Every inline comment's line must fall inside a diff hunk** or the API
rejects the whole review:

```
gh api "/repos/$REPO/pulls/<n>/files" --jq '.[] | "\(.filename)\n\(.patch)"'
```

Parse the `@@ -old +new,len @@` headers for new-side ranges and check each target line. For a
finding on an unchanged line, anchor to the nearest changed line in a related file and cite the real
`path:line` in the comment text. (Worked example: a finding in a task script the diff never touched,
anchored onto the workflow line that exports the env var it concerns.)

Build the payload with a script, not by hand, so escaping is right:

```
commit_id: <gh api "/repos/$REPO/pulls/<n>" --jq .head.sha>
event:     "COMMENT"          # never APPROVE
body:      <the body>
comments:  [{path, line, side: "RIGHT", body}, ...]
```

Write it to the scratchpad, validate with `python3 -c "import json;json.load(open(...))"`, then:

```
gh api --method POST "/repos/$REPO/pulls/<n>/reviews" --input review.json
```

**Verify the anchors landed.** The `/reviews/<id>/comments` endpoint reports `line: null` and
populates only `position`, which is normal and not a failure. Confirm real line numbers through the
canonical endpoint:

```
gh api "/repos/$REPO/pulls/<n>/comments?per_page=100" \
  --jq '.[] | select(.pull_request_review_id==<review_id>) | "\(.path):\(.line) side=\(.side)"'
```

If a comment came back unanchored, say so rather than reporting success.

## Step 7: Hand back what is not yours

Report the review URL, then:

- **The verdict.** Unset, with the command ready:
  `gh pr review <n> --approve -b "..."` or `--request-changes -b "..."`. Give a recommendation and
  the argument on both sides; do not choose. Approve-with-comments is the common case; request
  changes only for dangerous, incomplete or broken work, since it forces another cycle.
- **Tracker follow-ups.** Written up and ready to file, deliberately kept out of the payload, since
  a follow-up needs a real home and a comment on a merged PR is not one. Offer to create them.

## Do not

- Post before the drafts have been read.
- Select APPROVE.
- Paste raw findings output into the PR. Filtering is the whole job.
- Put missing tests, missing docs or scope-creep observations in PR comments instead of the tracker.
- Reformat or "improve" wording the reviewer supplied.
