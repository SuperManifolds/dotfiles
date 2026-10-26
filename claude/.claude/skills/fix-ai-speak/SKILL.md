---
name: fix-ai-speak
description: Strip the tells that make prose read as AI-written, and add back the habits human writers have that LLMs underuse. Use when asked to de-slop, de-AI, or humanise a draft, when writing anything that goes out under a person's name (PR comments, review bodies, commit messages, tickets, docs, Slack), and as a final pass before posting. Works on short technical prose; it edits text, never code.
argument-hint: "[file or paths to scan (default: the drafts in the conversation)]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Edit `$ARGUMENTS`, or the drafts under discussion, to remove the patterns that mark prose as
LLM-written. The goal is not to defeat a detector. It is that text going out under a person's
name should read like that person wrote it, and the same patterns that read as AI also read as
padded, so removing them makes the writing better.

Scope: short prose. Review comments, PR bodies, commit messages, tickets, docs, chat. Not code,
not identifiers, not quoted material from someone else.

## The one rule that matters: count, don't eyeball

Every other instruction here is subordinate to this. The tells that survive a read-through are
the ones above sentence level, and you cannot see those by reading, because reading one sentence
at a time is exactly the wrong granularity for spotting that every sentence has the same shape.

This is not hypothetical. In the session this skill came out of, the drafts were declared free of
rule-of-three constructions twice, by eye, on a careful read. Both times that was wrong: the
review body had three `, so X.` closers and three parallel evidence blocks each resolving to a
verdict, and one comment had three parallel `so` consequences. The sentences were fine. The
paragraphs were a formula. `scan.py` found it in one command.

So: run the scanner before you claim anything about a draft, and run it again after editing.
Never report a draft as clean on the strength of having read it.

## Step 1: get the text into a file, one block per unit

Blank lines separate blocks, and each block is scored on its own. Put each comment, each
paragraph, each message in its own block so a formula that repeats across them is visible as a
repeated hit rather than averaged away.

Write the drafts to a scratch file rather than scanning the source document, so the report is
about the prose and not about surrounding markup.

**Blank lines, not newlines.** A draft with one paragraph per line scans as a single block, and a
single block averages away the paragraph-level formula the scanner exists to find. This is easy to
get wrong and silent when you do: `awk 'NF{print; print ""}' draft.txt > blocks.txt` fixes it. If a
report comes back with one block for a multi-paragraph draft, you have not scanned it yet.

## Step 2: scan

```
python3 ~/.claude/skills/fix-ai-speak/scan.py draft.txt
```

Takes several files, or `-` for stdin. It strips inline code spans, fenced blocks and block
quotes first, so identifiers and quoted material do not pollute the counts. For each block it
reports tier A hits, tier B hits, sentence-length spread, and which human counter-signals are
present or absent.

The scanner has no idea what a quotation is, so a document that *discusses* these patterns
lights up with its own examples. Scanning this file reports participial tails and AI vocabulary
because it lists them. Judge the hits, do not total them.

Read the numbers, not just the flags. `sentence-length CV` below 0.35 means every sentence is
the same length, which is its own tell even when no individual sentence is wrong.

## Step 3: fix, by tier

**Tier A, strike on sight.**

- *Sycophantic or filler opener.* "Great question", "You're absolutely right", "Thanks for
  raising this." Delete everything before the first informative sentence. Measured at 0 per 10k
  human words against 94 for AI.
- *Markdown bold, headers, emoji, decorative Unicode* inside a short message. Bold phrases run
  43x the human rate, headers 23x, and some emoji over 900x. Three sentences do not need a
  bold label per point. Prose.
- *Present-participial tail clause*: "..., ensuring X", "..., highlighting Y", "..., allowing Z".
  The strongest grammatical discriminator measured anywhere, GPT-4o at 527% of the human rate,
  rank 1 of 66 Biber features. Cut the tail or promote it to its own sentence with a real subject.
- *Closing restatement.* "In short", "Overall", "This ensures that..." In anything under about
  150 words the reader can see the whole thing; there is no summary sentence.
- *Parallel consequence clauses.* Three `, so X` endings in a paragraph is a formula. Keep one,
  rewrite the others as bare facts, or let a sentence just stop.
- *Uniform item shape.* Equal-length, equal-shape items. Real findings are unequal and deserve
  unequal text. Make the short one short.

**Tier B, reliable only in clusters. One alone proves nothing.**

AI vocabulary (*crucial, comprehensive, robust, seamless, leverage, ensure, underscore,
showcase, delve*): three in a paragraph is the threshold. Negative parallelism ("not just X but
Y", "it's not A, it's B"): only 3x by count but the pattern humans recognise fastest.
Triads. Nominalization and copula avoidance ("serves as" for "is", "provides validation for" for
"validates"). Over-signposting. Rhetorical questions you then answer. Verbosity relative to
information.

The scanner over-matches on triads, because a real three-item list and a rhetorical triad look
identical to a regex. Look at each hit. A list of three things that exist is fine; three
adjectives where the third is padding is not.

## Step 4: add the counter-signals, do not just subtract

Removing tells leaves text that is merely neutral. What makes prose read as human is the
presence of habits LLMs underuse. Rates are GPT-4o against a human baseline of 100%:

**Never insert one to clear a flag.** The scanner reporting `because: absent` is a diagnosis, not a
task. If the paragraph states results and makes no causal claim, absent is the correct answer, and
manufacturing a reason to satisfy the tool produces a sentence written for the tool rather than the
reader. It shows: the clause that got written this way was "LiveKit ran live because the keys were
on the box", which told the author of the pull request nothing and leaked the reviewer's own process
into a review body. Reach for these where the link is real and the reader wants it, and leave the
flag standing otherwise.

- **"because" at 20%**, the single most underused word measured. Say *because*, not *thereby
  enabling* or *as this ensures*. If you removed a participial tail in step 3, *because* is
  usually what belongs there.
- Pro-verb "do" (26%), synthetic negation "no caller checks this" (51%), amplifiers
  *really/very* (46%), second person (52%), informal hedges *about/roughly* (50-63%),
  agentless passives (53%), bare demonstrative "This breaks on aarch64" (50%), first person
  (62%), contractions (60%), clausal coordination "..., but I..." (59%).
- **First-person uncertainty about your own work.** "I didn't run this on the real hardware."
  "I might be wrong about which leg that hits." A genuine human marker, unlike "it could be
  argued that". Only ever state uncertainty you actually have.
- **Specific numbers with no framing.** `46 bytes`, `line 1935`, `kernel 6.12.101`, a commit SHA.
  Models generalise, people cite.
- **Asymmetry.** One finding gets four sentences, the next gets three words. Sentences that stop.
- **Cost-of-fix reasoning and history.** "Not worth fixing, it goes away with #1226."

## Step 5: what not to strip

Voice beats this skill. If there is a corpus of how this person actually writes (past PR
comments, past commits, past messages), fetch it and match it, and let it override any rule
here. A house opener that looks sycophantic on the list but appears in four of that person's
four real review bodies stays.

Also leave alone: quoted text from someone else, real three-item lists, em dashes in a document
that already uses them, code and identifiers, and technical terms that only look like AI
vocabulary. Strip a pattern because it is dense and unearned in this draft, not because the
character or word is on a list.

Do not flatten the text into terseness for its own sake. Length should track evidence. A comment
carrying a real measurement is allowed to be long; a comment carrying an opinion is not.

## Step 6: re-scan, and say what changed

Run the scanner again and report the deltas, not an assurance. "Three `, so X` closers down to
one, sentence-length CV 0.55 to 0.61" is a result. "Cleaned up the AI-sounding phrasing" is not,
and it is the exact claim that was wrong twice in the session that produced this skill.

## Caveats worth stating when you report

- **Em dashes have fallen out of the reliable tier.** Still 10x by one vendor's count, but Gemini
  3 Pro is now below the human rate and GPT-5.1 suppresses them. Corroborating evidence only.
  Remove them if the draft is dense with them, not on principle.
- **The folklore that AI hedges more is mismeasured.** LLMs use informal approximators at 50-63%
  of the human rate. They underuse *because*, pro-verb *do*, and contractions far more.
- **Human unaided detection is near chance.** Editing your own text to remove tells is worth
  doing. Concluding that someone else's text is AI from these tells is not, and this skill must
  never be used to make that accusation.
- **The tells age fast.** *Delve* peaked in 2023-24 and collapsed. Any word list here is a
  snapshot, and human writing is measurably converging on LLM style anyway.

`references/tells.md` has the full checklist, the per-tell effect sizes, before/after rewrites
and 35 sources, graded by whether each is corpus-measured, corroborated or folklore. Read it when
a call is close or when the scanner flags something the guidance above does not cover.
