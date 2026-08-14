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

The pipeline is: read the authority → verify → filter → classify → **inventory, the reviewer cuts** →
draft → **the reviewer signs off** → post. The two gates are not ceremony; they are what makes the
comments legitimate, and the first one is what stops polished prose being written for findings that
are about to be cut.

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
- **Never choose the verdict yourself.** Default to handing back the command with a recommendation
  (Step 7). If the reviewer has read the drafts and explicitly tells you to approve, submit
  `--approve`: that is their decision and you are executing it, not making it. What stays forbidden
  is inferring an approval from silence, from "looks good", or from green CI. Refusing a direct,
  informed instruction to approve is its own failure, not caution.
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

Every number that reaches a draft (exit code, count, size, duration) gets re-derived with a second,
differently-shaped command before you write it down. Never read `$?` through a pipe: it reports the
last command in the pipeline, so `cmd | head` tells you about `head`. Drop the pipe, redirect to a
file, or use `PIPESTATUS`. A wrong measurement stated flatly in the reviewer's voice is the most
expensive mistake this skill can make, because it reads exactly as confidently as a right one.

When verification needs a credential you cannot hold, do not iterate single commands through the
reviewer. Write one read-only script, hand them the single command that runs it, and ask for the
output. Never ask for a token. If one gets volunteered anyway, use it without writing it to disk, and
tell them it is now in the transcript and worth revoking.

## Step 3: Filter hard

This is the step that gets skipped and it is the most important one. One high-signal finding beats
twenty plausible ones, and a review with twenty comments is a smell rather than thoroughness.

From the candidate set, keep only what a person should spend attention on. These are ceilings, not
quotas:

- **At most 2 blockers.** Dangerous, incomplete or broken. Label `blocker:`.
- **At most 5 flags.** Worth knowing, author decides. Label `flag:`.
- **At most 4 nits.** Small, take or leave. Label `nit:`.
- **Everything else → the issue tracker** (Step 7), not a PR comment.

A verification body with no inline comments at all is a complete, good review, and it is the common
outcome for a small, well-tested change. If all you have is wording preferences in a doc that is
already accurate enough to use, post the body and stop. Never pad toward the numbers above: working
to fill a shape is how invented nits get written, and the reviewer deletes them at the gate anyway.
If the repo's policy has a "when either way is acceptable, approve without a comment" principle, that
outranks any count in this skill.

Drop, do not post: findings on pre-existing code the diff only sits beside, style preferences that
cause no bug, missing tests and missing docs (tracker items), and anything where the realistic
worst case has no concrete harm.

Fold near-duplicates into one comment with several line references rather than one comment each.

Then ask, per survivor: is this faster to fix than to describe? Doc-only wording and one-line changes
usually are, and the repo's policy may well prefer the fix (pushing commits to the branch) over the
comment. Apply it locally, show `git diff`, and never commit or push without an explicit instruction.
On someone else's branch, say whose branch it is before proposing a push.

## Step 4: Draft

**Body.** Longer than an inline comment is fine. Structure that has worked:

1. One short clause of concrete praise, naming the author. Inline comments carry no praise, so this
   is the only place it goes. Keep it to a clause and make it trivially deletable, since reviewers
   often trim it to something plainer or cut it outright.
2. The blocker in two or three sentences, with the repro, ending `Details inline.`
3. What you verified, as a flat list of commands and results, plus what you did not run.
4. Anything worth knowing that is not a comment (e.g. a test cell that gives some path no
   coverage), and where it is going instead.

**Inline comments.** One per finding: `<label>: <observation>, <evidence>, <fix folded in>`. Lead
with the observation, no preamble, no narration of how you verified beyond the evidence itself.

## Step 5: Human review gate

Two phases, because polished prose thrown away is the most wasted work in this skill.

**Phase 1, the inventory.** Before writing any final prose, present a numbered list of survivors, one
line each:

```
F1  flag  README.md:17   tasks only exist inside this directory, root invocation dumps mise help
F2  nit   README.md:20   the `--` is not actually required for flags
```

Give every candidate a stable ID that cannot be read as a line number (`F1`, `F2`, …), and never
present a bare number that could mean either a finding or a line. Split a comment that bundles
several line references into `F2a` / `F2b`, so cutting half of it is expressible without prose. Then
get keep/cut decisions on the list.

**Phase 2, the drafts.** Write full prose only for what survived Phase 1, and present the body and
every comment **in the conversation**, as quoted blocks readable without opening a file. Do not post
yet.

Expect the reviewer to narrow more than once, including all the way down to zero comments, and treat
each narrowing as normal rather than as a restart. Re-present only what changed, and when they supply
wording, drop it in verbatim rather than reworking the sentence around it.

Then wait. Post only on an explicit instruction to post. If the drafts have not been read, there is
no instruction that authorises posting.

## Step 6: Post

With no inline comments, skip the payload entirely. Write the body to a file and let `gh` handle the
escaping, which also makes the command copy-pasteable for the reviewer to run themselves:

```
gh pr review <n> --comment --body-file <path>      # or --approve, per Step 0
```

With inline comments, resolve anchors first. **Every inline comment's line must fall inside a diff hunk** or the API
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
event:     "COMMENT"          # "APPROVE" only on an explicit instruction (Step 0)
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

- **The verdict.** Leave it unset unless the reviewer told you to submit it. Give a recommendation and
  the argument on both sides, then hand over the command:
  `gh pr review <n> --approve --body-file <path>` or `--request-changes --body-file <path>`.
  Recommending is yours, choosing is theirs, and executing is either. Approve-with-comments is the
  common case; request changes only for dangerous, incomplete or broken work, since it forces another
  cycle.
- **Tracker follow-ups.** Written up and ready to file, deliberately kept out of the payload, since
  a follow-up needs a real home and a comment on a merged PR is not one. Offer to create them.

## Do not

- Post before the drafts have been read.
- Select a verdict on your own initiative, or infer one from silence, "looks good", or green CI. When
  the reviewer explicitly asks for the approve, submitting it is correct, and refusing is not.
- Paste raw findings output into the PR. Filtering is the whole job.
- Pad the comment count toward the ceilings in Step 3. Zero inline comments is a valid review.
- Write final prose before the inventory has been agreed (Step 5, Phase 1).
- Put a bare `#N` in front of the reviewer when it could read as either a finding or a line number.
- Read `$?` through a pipe, or put any number in a draft that only one command ever produced.
- Put missing tests, missing docs or scope-creep observations in PR comments instead of the tracker.
- Reformat or "improve" wording the reviewer supplied.
