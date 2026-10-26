# AI tells in short technical prose: a mechanical editing checklist

Scope: code-review comments, PR descriptions, commit bodies, bug reports. Ordered by how
reliably each tell discriminates AI from human text in *short* prose. Each item: the tell,
why it reads as AI, a before/after in review register, and the evidence grade.

Evidence grades:
- **[M]** measured — corpus study or detector-vendor counts with numbers.
- **[C]** convergent — named independently by practitioners across several threads, plus a
  qualitative/observational source, but no clean effect size.
- **[F]** folklore — repeated widely, no measurement found. Use, but do not over-trust.

Before anything else, read the caveats at the bottom. Human unaided detection is poor, and
several classic tells are decaying fast.

---

## Tier A: high-discrimination. Strike on sight.

### A1. Sycophantic or validating opener **[M]**
**Tell:** "You're absolutely right", "Great question", "Thanks for the detailed feedback and
for raising these points", "Good catch!", "I'd be happy to".
**Why it reads as AI:** Near-zero human baseline for the canned forms, and the whole speech act
(validating the reviewer before answering) is an RLHF artifact, not review behaviour. Pangram
measured "Certainly! Here's" at 0 per 10k human words vs 94 for AI (70x), "I'd be happy to" at
5x, "Here's what you need to know" at 11x
(https://www.pangram.com/signs-of-ai-writing). It is the single most-named tell in the
r/ExperiencedDevs thread on AI-written PR replies, to the point of a suggested CI rule that
"automatically rejects PR that contain 'you're absolutely right'"
(https://www.reddit.com/r/ExperiencedDevs/comments/1nq5npn/my_coworker_uses_ai_to_reply_to_my_pr_review_and/).

> **Before:** You're absolutely right about the locking here, and thanks for the detailed
> context. The core issue is a race between the unlock and the retry.
> **After:** There's a race between the unlock and the retry.

Rule: delete every sentence before the first sentence that carries information.

### A2. Markdown emphasis and headers inside a short comment **[M]**
**Tell:** `**bold**` on a phrase mid-sentence, `###` headers, or a bolded label per point, in
a comment under a dozen lines.
**Why it reads as AI:** Pangram: markdown 8 vs 90 per 10k words (12x); bold specifically 2 vs
65 (43x); headers 0.5 vs 11 (23x). Bold is the highest single-feature multiplier in their whole
table. Humans reach for it in docs, not in a three-sentence review note.
**Nuance for GitHub:** markdown renders in the comment box, so its presence is not itself the
tell. The tell is *density and shape*: a bolded noun phrase used for emphasis rather than for a
code identifier, and a header structure imposed on content too short to need one.

> **Before:** **Issue:** the mutex is released early. **Impact:** a concurrent writer can
> observe a torn struct. **Suggested fix:** move the `Unlock` after the copy.
> **After:** The mutex is released before the copy, so a concurrent writer can see a torn
> struct. Move the `Unlock` below line 214.

### A3. Emoji and decorative Unicode **[M]**
**Tell:** ✅ ⚠️ 🚀 in a comment; also `→`, `≈`, `≥`, `─` box-drawing, and other characters not
on the keyboard.
**Why it reads as AI:** Pangram: unusual Unicode 28 vs 71 per 10k (3x overall), but the
per-character multipliers are extreme: `─` 940x, `≈` 241x, `⚠` 57x, `→` 48x. Developers treat
it as near-conclusive: "if the comment has an emoji it's a guarantee", quoted in Baltes, Cheong
and Treude's coding of 1,154 Reddit/HN posts (https://arxiv.org/html/2603.27249v3), and echoed
in the review threads ("I have a pull request with 6000 lines of code. It has emojis").

> **Before:** ✅ Fixed the leak. ⚠️ Note: this changes the exported signature.
> **After:** Fixed the leak. This changes the exported signature.

Replace `→` with "to" or "becomes", `≈` with "about", `≥` with ">=" in prose.

### A4. Present-participial tail clause ("..., ensuring X", "..., highlighting Y") **[M]**
**Tell:** A sentence that states a fact and then appends an `-ing` clause explaining what the
fact means, ensures, enables, reflects, or underscores.
**Why it reads as AI:** This is the strongest *grammatical* discriminator measured. Reinhart et
al., PNAS 2025 (preprint https://arxiv.org/html/2410.16107v1, Table 3) scored 66 Biber features
by classifier importance; present participial clauses ranked first, with GPT-4o using them at
**527%** of the human rate (GPT-4o Mini 481%). Postnominal participials 243%, past participials
307%. Wikipedia's community guide files the same pattern under "Superficial analyses", with
words to watch: *highlighting / underscoring / emphasizing / ensuring / reflecting /
contributing to / enhancing*
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Superficial_analyses).

> **Before:** The retry loop now backs off exponentially, ensuring the service is not
> overwhelmed during partial outages.
> **After:** The retry loop now backs off exponentially. Without it we hit the API 200x/s
> during the 03:14 outage.

Rule: if an `-ing` clause hangs off the end of a sentence and tells the reader what to think
about the main clause, cut it. If the content matters, make it its own sentence with a fact in
it.

### A5. The closing restatement **[C]**
**Tell:** A final sentence beginning "In short,", "Overall,", "Ultimately,", "To summarize,"
or "This ensures that..." that adds nothing to a message the reader can see in full.
**Why it reads as AI:** Models close sections by habit regardless of length. The top-voted
reaction in the PR-reply thread is exactly this: "The 'in short' after 500 words of ai-slop is
already pissing me off"
(https://www.reddit.com/r/ExperiencedDevs/comments/1nq5npn/my_coworker_uses_ai_to_reply_to_my_pr_review_and/).
Wikipedia catalogues the article-scale version as "Outline-like conclusions about challenges
and future prospects"
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Outline-like_conclusions_about_challenges_and_future_prospects).

> **Before:** ...so the fix is to seed the slice before the patch. In short, this makes the
> ack path work as intended while preserving the existing behaviour.
> **After:** ...so the fix is to seed the slice before the patch.

Rule: in a comment under ~150 words, there is no summary sentence. Delete it.

### A6. Uniform item shape across a list **[M for bullets, C for the symmetry]**
**Tell:** Three or four points, each the same length, each the same grammatical shape, each
with the same label-colon-explanation structure. Or a bulleted list where two clauses of prose
would do.
**Why it reads as AI:** Pangram measured bullet lists at 3 vs 28 per 10k words (9x). The
symmetry itself is the deeper tell: real review findings are unequal in importance and get
unequal amounts of text. Wikipedia notes LLMs "use this structure to make superficial analyses
appear more comprehensive".

> **Before:**
> - **Correctness:** the offset is computed before the guard page is mapped.
> - **Performance:** the extra syscall adds latency to the hot path.
> - **Style:** consider extracting a helper.
> **After:** The offset is computed before the guard page is mapped, so this faults on the
> first restore after a 2MB-aligned mapping. The extra syscall and the helper extraction are
> both fine as-is.

---

## Tier B: reliable in clusters. One alone proves nothing.

### B1. "AI vocabulary" density **[M]**
**Tell:** *crucial, comprehensive, robust, seamless, leverage, ensure, enhance, underscore,
showcase, delve, intricate, pivotal, notably, additionally, particularly, insights, align with,
significant, key (adj), landscape, tapestry, testament*.
**Why it reads as AI:** Kobak et al. compared 14M PubMed abstracts 2010-2024 against a
counterfactual extrapolated from 2021-22 (https://arxiv.org/html/2406.07016v1; published in
Science Advances 2025). Excess frequency ratios in 2024: *delves* r=25.2, *showcasing* r=9.2,
*underscores* r=9.1. Excess frequency gaps for common words: *potential* δ=0.041, *findings*
δ=0.027, *crucial* δ=0.026. They found 280 excess *style* words in 2024, of which 66% verbs and
18% adjectives, versus prior years where excess words were content nouns. Ten common words
alone (*across, additionally, comprehensive, crucial, enhancing, exhibited, insights, notably,
particularly, within*) recover a 9.8-point frequency gap. Juzek and Ward, COLING 2025, confirm
the set and fail to trace it to architecture or training data, finding mixed support for RLHF
(https://aclanthology.org/2025.coling-main.426.pdf). Wikipedia maintains era-sorted lists and
notes *delve* dropped off sharply in 2025, so the specific words age
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#High_density_of_%22AI_vocabulary%22_words).
Full 900-word annotated list: https://github.com/berenslab/chatgpt-excess-words

> **Before:** This is a crucial fix that ensures robust handling of the restore path and
> provides valuable insights into the underlying race.
> **After:** This fixes the restore path. The race is between `Unlock` and the retry, not in
> the page-server as the issue claims.

Rule: one of these words is nothing. Three in a paragraph is a tell. Note that synonyms are
*not* implicated: "underscore" is flagged, "stress" is not.

### B2. Negative parallelism: "not just X, but Y" / "It's not A, it's B" **[M]**
**Tell:** Contrastive negation used to elevate a point.
**Why it reads as AI:** Pangram: 1 vs 3 per 10k words (3x). The multiplier is modest but
recognition is near-universal: it is the most-cited pattern in both the r/WritingWithAI
megathread and the r/ClaudeAI detection thread, where one commenter argues it beats the em dash
because "this contrast structure is so embedded in AI that it affects syntax globally, even
without em dashes present"
(https://www.reddit.com/r/WritingWithAI/comments/1mqse0s/megathread_what_aiisms_give_away_aigenerated/,
https://www.reddit.com/r/ClaudeAI/comments/1m259dh/what_are_your_main_tipoffs_for_detecting_ai/).
Wikipedia catalogues three variants: *not just X but also Y*, *not X but Y*, *Y rather than X*
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Negative_parallelisms).

> **Before:** This isn't just a style nit, it's a correctness problem.
> **After:** This is a correctness problem.

### B3. Triads **[M]**
**Tell:** Three adjectives, three noun phrases, three clauses, especially when the third is
padding.
**Why it reads as AI:** Pangram: 5 vs 19 per 10k words (4x). Wikipedia notes the tell is
stronger "in contexts where most people would not bother to include such stylistic flourishes,
like edit summaries", which is exactly the register of a review comment.
**Honest caveat:** the rule of three is ancient and legitimate. What is anomalous is rate, not
presence, so this only counts when you have two or three triads in one comment.

> **Before:** The change is clean, correct, and well tested.
> **After:** The change is correct. Tests cover the 2MB case but not the unaligned one.

### B4. Nominalization and copula avoidance **[M]**
**Tell:** "provides validation for" instead of "validates"; "serves as the entry point" instead
of "is the entry point"; "performs an initialization of" instead of "initializes".
**Why it reads as AI:** Reinhart et al. measured nominalizations at 209-214% of the human rate
for GPT-4o, and "be as main verb" at only 61-63%. Wikipedia cites a study finding an over-10%
decrease in *is*/*are* in academic writing in 2023, with GPT-3.5 reliably removing them when
asked to "revise the following sentence"
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Avoidance_of_basic_copulatives_(%22is%22/%22are%22_phrases)).
Words to watch: *serves as, stands as, functions as, represents, boasts, features, offers,
maintains*.

> **Before:** This helper serves as the primary mechanism for the performance of state
> reconciliation.
> **After:** This helper reconciles state.

### B5. Over-signposting **[M for the words, C for the density]**
**Tell:** "Additionally,", "Moreover,", "Furthermore,", "It's worth noting that", "That said,",
"In the context of" opening consecutive sentences.
**Why it reads as AI:** *Additionally* is in Kobak's ten highest-gap common words; Wikipedia
lists it first among words to watch, flagging sentence-initial position specifically. Four
sentences in a row each opening with a connective is a shape humans rarely produce in a comment
box.

> **Before:** Additionally, the timeout is hard-coded. Moreover, it's worth noting that the
> caller already has a deadline. Furthermore, this duplicates the retry logic in `client.go`.
> **After:** The timeout is hard-coded even though the caller already has a deadline, and it
> duplicates the retry logic in `client.go`.

### B6. Rhetorical question answered immediately **[C]**
**Tell:** "Why does this matter? Because...", "The tell? This.", "Is this a blocker? Yes."
**Why it reads as AI:** Named repeatedly and independently ("That rhetorical question? Here's
the immediate answer", "the very short question followed by the answer... Obvious AI writing?
It sure as hell is") in the megathread and the r/ClaudeAI thread. No corpus number found.

> **Before:** Why does this matter? Because the restore path runs before the mount namespace
> is set up.
> **After:** The restore path runs before the mount namespace is set up.

### B7. Explaining significance instead of stating the fact **[C]**
**Tell:** Sentences whose content is an assessment of importance rather than an observation:
"This is an important consideration for maintainability", "This demonstrates good separation of
concerns."
**Why it reads as AI:** Wikipedia's framing is the clearest statement of the mechanism: models
"regress to the mean", omitting specific, statistically rare facts and replacing them with
generic, positive, important-sounding language, so the subject becomes "simultaneously less
specific and more exaggerated"
(https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Content). In review, this shows up
as praise or significance-claims with no referent.

> **Before:** Nice separation of concerns here, this will really help maintainability.
> **After:** (delete, or) Moving the parser out means the fuzzer can target it directly.

### B8. Symmetric praise-then-criticism and both-sides closing **[F]**
**Tell:** Every criticism preceded by a compliment of matching weight; a conclusion that the
answer "depends on the context."
**Why it reads as AI:** Practitioner consensus: "they give a nuanced take to both sides of the
topic, and at the end conclude with 'Overall it depends on many factors'... When humans say
things in the real world, they are usually trying to make a single point"
(https://www.reddit.com/r/ClaudeAI/comments/1m259dh/what_are_your_main_tipoffs_for_detecting_ai/).
No measurement found. Real reviewers are asymmetric: they praise one thing in ten and then
argue one position.

> **Before:** Great use of the context here! One small thought: the deadline may not propagate.
> Either approach works depending on the call site.
> **After:** The deadline doesn't propagate through `spawnWorker`. Pass `ctx` at line 88.

### B9. Em dash overuse **[M, but decaying and model-dependent]**
**Tell:** `—` used two or more times in a short comment, usually space-padded, where a comma,
colon, or parenthesis would do.
**Why it reads as AI:** Pangram measured 2 vs 17 per 10k words overall (10x), with a human
baseline of 5 and per-family rates of OpenAI 45 (9x), open-source 37 (8x), Anthropic 32 (7x).
Independently, Keck sampled 10,000 ecology abstracts from OpenAlex in 2021 vs 2025 and found em
dash relative frequency "more than doubled", the only character in a wide punctuation set to
rise steeply (https://www.pieceofk.fr/the-rise-of-the-em-dash-in-ecology-abstracts/).
**Why to discount it anyway:** the signal is collapsing. Pangram's own table puts Gemini 3 Pro
at 3 per 10k, *below* humans. Wikipedia has flagged the section as a candidate for its
"historical indicators" list, notes GPT-5.1 suppresses em dashes, and cites a July 2026 study
finding only Claude exceeds professional writers. Meanwhile many humans use em dashes heavily
and resent the accusation. Treat as corroborating evidence only, never as primary.

> **Before:** The lock is released early — before the copy — so a writer can observe a torn
> struct.
> **After:** The lock is released before the copy, so a writer can observe a torn struct.

### B10. Verbosity relative to information content **[C]**
**Tell:** Five paragraphs where three sentences would do; restating the reviewer's point back
to them before answering it.
**Why it reads as AI:** The most-upvoted heuristic in the PR-reply thread: "LLMs are so fucking
wordy, the best way to tell if a human wrote something is if it's terse." Baltes et al. code
"verbose style" and "step-by-step commenting" as explicit reviewer detection markers
(https://arxiv.org/html/2603.27249v3). Also the highest-value edit you can make regardless of
detection.

---

## Counter-signals: what human technical prose has that LLM prose lacks

These are the positive things to *add*, not just tells to remove. Rates below are GPT-4o
relative to the human baseline in Reinhart et al. Table 3 (https://arxiv.org/html/2410.16107v1)
(100% = human parity; lower means the model underuses it).

| Human habit | GPT-4o rate | How to use it |
| --- | --- | --- |
| **"because"** | **20%** | Say *because*, not *as this ensures* / *thereby enabling*. The single most underused word in the table. |
| Pro-verb "do" | 26% | "It doesn't" rather than "this does not perform the operation". |
| Synthetic negation (*no X is...*) | 51% | "No caller checks this." |
| Amplifiers (*very, really*) | 46% | "This is really only safe under the lock." |
| Second-person pronouns | 52% | "You're relying on map ordering here." |
| Informal hedges (*about, roughly, almost*) | 50-63% | "about 40ms", "roughly two allocations per call". |
| Agentless passives | 53% | "The fd gets closed twice." |
| Demonstrative pronouns (bare *this*/*that*) | 50% | "This breaks on aarch64." not "This behaviour introduces a regression on aarch64." |
| First-person pronouns | 62% | "I couldn't reproduce this on 6.12." |
| Contractions | 60% | "doesn't", "isn't", "won't". |
| Clausal coordination (*..., but I...*) | 59% | LLMs prefer *phrasal* coordination (194%): "clean and correct". Humans join clauses. |
| Sentence relatives (*..., which is why...*) | 50% | |
| "if / unless" | 60% | Real conditions: "unless the mount is shared". |
| Adverbs | 82% | |

Five more counter-signals with no clean measurement **[F/C]**, all named repeatedly by
practitioners:

1. **Specific numbers with no framing.** "40ms", "line 214", "kernel 6.12.94 on aarch64", a
   commit SHA. Models generalize; humans cite. Wikipedia's regression-to-the-mean argument
   predicts exactly this gap.
2. **Unexplained jargon.** Humans write to a peer and assume shared context. Models gloss.
   Delete any clause that defines a term your reader already knows.
3. **Admitted uncertainty about your own work.** "I'm not sure this is the right layer for it."
   "This might be a red herring." Note that the Biber *hedges* feature above measures
   informal approximators, not epistemic stance; Jiang and Hyland, cited by Reinhart, found
   ChatGPT produces *fewer* epistemic stance markers and fewer human subjects. So first-person
   uncertainty is a genuine human marker, while "it could be argued that" is not.
4. **Asymmetry and abrupt shifts.** One finding gets four sentences, the next gets three words
   ("also: typo line 9"). Sentences that just stop. No transition between them.
5. **Cost-of-fix reasoning and history.** "Not worth fixing now, it's going away with #1226."
   "We hit this in the 07-14 test." Models have no stake and no memory of the project.

---

## Caveats: what not to over-claim

- **Human unaided detection is weak.** A 2025 study found humans at chance level distinguishing
  LLM from human text; a German thesis study found 57% recognition for AI text and 64% for
  human. Heavy LLM users reach ~90%, light users barely beat chance
  (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing#Your_detection_ability).
  Editing to remove tells is worthwhile; concluding that someone else's text is AI from tells
  alone is not.
- **No single tell is decisive.** Pangram states it plainly: "No single tell of AI writing is a
  giveaway", and their production detector does not use these features as inputs. Developers
  agree: "All these tells alone don't tell you anything, but seeing multiple of them is a pretty
  good tell."
- **The tells age, fast.** *Delve* peaked in 2023-24 and collapsed in 2025. Em dashes are being
  actively suppressed by vendors. Any word list here is a 2026 snapshot.
- **Human writing is converging on LLM style.** Kobak's own conclusion is that the effect on
  scientific vocabulary exceeded the Covid pandemic's; measurable LLM influence has been found
  in spoken podcast content. Some of what reads as AI in 2026 is just how people write now.
- **Beware self-inflicted false positives.** Em dashes, semicolons, bullet points, and the rule
  of three are all legitimate. Strip them because they are *dense and unearned* in your draft,
  not because the characters are forbidden.
- **The listicle problem.** Most "10 signs of AI writing" pages recycle an unsourced list and
  are themselves AI-written. Everything graded **[M]** above traces to a corpus with a method:
  Kobak et al. (14M PubMed abstracts), Reinhart et al. (HAP-E corpus, 66 Biber features),
  Juzek and Ward (COLING 2025), Keck (10k ecology abstracts), Pangram (vendor, millions of
  documents, self-interested but the only source with per-tell multipliers), Baltes/Cheong/
  Treude (1,154 coded developer posts).

---

## Sources

Corpus and detection research
- Kobak, González-Márquez, Horvát, Lause, "Delving into ChatGPT usage in academic writing
  through excess vocabulary" — https://arxiv.org/html/2406.07016v1 ; word list:
  https://github.com/berenslab/chatgpt-excess-words
- Reinhart et al., "Do LLMs write like humans? Variation in grammatical and rhetorical styles",
  PNAS 2025 — https://www.pnas.org/doi/10.1073/pnas.2422455122 ; preprint with Table 3:
  https://arxiv.org/html/2410.16107v1
- Juzek and Ward, "Why Does ChatGPT 'Delve' So Much? Exploring the Sources of Lexical
  Overrepresentation in Large Language Models", COLING 2025 —
  https://aclanthology.org/2025.coling-main.426.pdf
- Keck, "The Rise of the Em Dash in Ecology Abstracts" —
  https://www.pieceofk.fr/the-rise-of-the-em-dash-in-ecology-abstracts/
- Pangram Labs, "9 Signs of AI Writing, Backed by Data" —
  https://www.pangram.com/signs-of-ai-writing

Style guides and community guides
- Wikipedia, "Signs of AI writing" (community-maintained, each claim source-linked) —
  https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing

Technical writing and code review specifically
- Baltes, Cheong, Treude, "'An Endless Stream of AI Slop': How Developers Discuss the Burden of
  AI-Assisted Software Development" (qualitative coding of 1,154 Reddit/HN posts; see the
  `ai-content-detection` code) — https://arxiv.org/html/2603.27249v3

Practitioner threads used
- r/ExperiencedDevs, "My coworker uses AI to reply to my PR review and I hate it" —
  https://www.reddit.com/r/ExperiencedDevs/comments/1nq5npn/my_coworker_uses_ai_to_reply_to_my_pr_review_and/
- r/ExperiencedDevs, "Reviewing someone else's AI slop" —
  https://www.reddit.com/r/ExperiencedDevs/comments/1nfpb14/reviewing_someone_elses_ai_slop/
- r/ExperiencedDevs, "AI Slop PRs are burning me and my team out hard" —
  https://www.reddit.com/r/ExperiencedDevs/comments/1kr8clp/ai_slop_prs_are_burning_me_and_my_team_out_hard/
- r/WritingWithAI, "MEGATHREAD: What AI-isms give away AI-generated writing?" —
  https://www.reddit.com/r/WritingWithAI/comments/1mqse0s/megathread_what_aiisms_give_away_aigenerated/
- r/ClaudeAI, "What are your main tip-offs for detecting AI writing?" —
  https://www.reddit.com/r/ClaudeAI/comments/1m259dh/what_are_your_main_tipoffs_for_detecting_ai/
