---
name: linear-issue
description: "Turn something from this conversation into a Linear issue, of any kind: bug, improvement, chore, investigation, docs, follow-up, or customer request. Extracts the ask from what was actually said, searches for issues that already cover it, copies the team/project/label conventions from neighbouring tickets, links the pull requests and sources it came from, and files it. Also updates an existing issue. Use when asked to file, create, draft, or update a Linear issue or ticket."
argument-hint: "[what to file, or an issue id to update]"
allowed-tools: Bash, Read, Grep, Glob, Write, Edit, ToolSearch, mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__get_issue, mcp__claude_ai_Linear__save_issue, mcp__claude_ai_Linear__save_comment, mcp__claude_ai_Linear__list_comments, mcp__claude_ai_Linear__list_teams, mcp__claude_ai_Linear__list_projects, mcp__claude_ai_Linear__list_issue_labels, mcp__claude_ai_Linear__list_issue_statuses, mcp__claude_ai_Linear__list_milestones, mcp__claude_ai_Linear__prepare_attachment_upload, mcp__claude_ai_Linear__create_attachment_from_upload
---

Turn `$ARGUMENTS`, or the thing this conversation just landed on, into a Linear issue. When
`$ARGUMENTS` names an existing issue, go to step 12 instead.

The input is usually **the conversation**, not a filesystem. Something got discovered, decided,
deferred, or asked for, and it needs to outlive the session. The job is to carry that across without
distortion: what is settled stays settled, what is a guess stays a guess, and whoever made a call gets
to keep having made it.

Writing to Linear is outward facing: teammates get notified, it lands in a cycle, and a bad issue costs
someone else a triage read. So the order is **extract, search, draft, file**. The two failures that
dwarf bad prose are that the issue already exists, and that a guess got filed as a fact.

If `mcp__claude_ai_Linear__*` is not available, find the equivalents with `ToolSearch("linear issue")`;
the server may be named differently. If there is no Linear server at all, say so rather than writing a
file and calling it filed.

## Steps

1. **Extract the issue from the conversation, and settle what kind it is.** Re-read what was actually
   said rather than what you would have said. Separate:
   - **the ask**: the one thing that has to change or be answered
   - **what is settled**, and by whom. A decision the human made is theirs; do not restate it as your
     recommendation, and do not quietly upgrade your suggestion into their decision
   - **what is open**, which becomes the open questions rather than being silently resolved
   - **what is out of scope**, especially anything explicitly declined, since the next reader will
     otherwise propose it again

   The kind drives the shape in step 6, so name it now:

   | kind | the issue answers | typical labels |
   |---|---|---|
   | Bug | what is broken, how it fails, how to see it | `Bug` |
   | Improvement or feature | what should exist, and what it unblocks | `Improvement`, `Feature` |
   | Chore or maintenance | what needs doing, and what forces it now | `Chore` |
   | Investigation or spike | the question to answer, and what a good answer looks like | `Spike`, `Research` |
   | Docs | what is wrong or missing, and who is misled by it | `Documentation` |
   | Follow-up | what was deliberately left, and why it was safe to leave | inherit from the parent work |
   | Customer request | what they asked for, in their words, and the constraint behind it | `CUSTOMER` |

   If the conversation produced several of these, they are several issues: file the parent first and
   give the children its `parentId` (step 10).

2. **Read the rules that already exist**, rather than inferring them from a handful of tickets.
   ```bash
   grep -rli "linear" rfd/ docs/ CONTRIBUTING.md CLAUDE.md AGENTS.md .claude/ 2>/dev/null | head
   ```
   Repos routinely specify who assigns, which state a started issue takes, and that the branch name
   must come from the issue so the two auto-link. Then resolve the destination:
   ```
   list_teams / list_projects / list_issue_labels / list_issue_statuses
   ```
   Read the label list rather than concluding nothing fits: a component label often sits past the
   default page.

   **Choosing the team**, when the workspace has more than one: take the team that owns the code or the
   surface the ask touches, which is usually the one that owns the component label or the project. When
   two could own it, file with the team that will do the work and relate it rather than filing twice.
   When it is genuinely unclear, ask. A misfiled issue is invisible to the people who need it.

3. **Search for what already covers it, at a weight that matches the blast radius.** One query for a
   typo or a one-line fix. Symptom plus component for something scoped to one area. The full sweep for
   anything subsystem-wide, customer-facing, or that another person would want to know about, which is
   also where a duplicate costs the most.

   The full sweep is four angles, because each surfaces tickets the others miss: the **ask** as a
   colleague would phrase it, the **mechanism or subsystem**, the **component** by label or project
   rather than by keyword, and the **exact identifier** (function, file, error string, feature name).

   `query` matches **title and description text only**, so a thing phrased differently in both will not
   be found. That is why the component angle has to be a listing:
   ```
   list_issues({project: "<project>", updatedAt: "-P14D", fields: ["title","assignee","status","url"]})
   list_issues({label: "<component>", includeArchived: true, fields: ["title","status","url"]})
   ```
   **Do not filter by state**, so completed and canceled issues come back too: a closed match can mean
   the thing is already done, or that the team declined it, and refiling something declined is worse
   than a plain duplicate. `includeArchived` is a separate axis, covering issues that were archived
   rather than closed.

   `get_issue` every candidate and read its **description, not its title**. On a close match, read
   `list_comments` too: the thing may already be diagnosed, declined, or half fixed in the thread
   rather than in the description. Then:

   | what you found | what to do |
   |---|---|
   | Same thing, open | Do not file. Add what this conversation learned to that issue, and say so. |
   | Same thing, someone else mid-flight | Leave it. Speak up only if your finding would waste their work, and keep it short. |
   | Related but distinct | File, relate it in step 10, and say in the text how the two differ. |
   | Same root cause, different half | File, and be explicit about which half this issue owns. Link both ways. |
   | Closed as done or declined | Do not refile silently. Reopen, or file and reference it. |
   | Nothing | File. |

   Put the searches in the draft as a table, so the reviewer can see the negative result was earned:
   ```
   | query or listing            | hits | verdict                         |
   |-----------------------------|------|---------------------------------|
   | "<distinctive term>"        | 2    | ARCH-1300 is the parent problem |
   | label:<component> -P14D     | 11   | none about this path            |
   ```

4. **Learn the shape, then read one exemplar of the same kind in full.** `get_issue` two or three issues
   in the same project, ideally under the same parent, and copy rather than invent: `team`, `project`,
   `parentId`, the label vocabulary in use, the estimate scale, and the priority norms. Then pick the
   closest in kind to what you are filing and imitate its structure and register. Reading one good issue
   teaches the house voice faster than any description of it can.

5. **Label every claim by how you know it.** Let the text show which is which:
   - **measured**: you ran it. Quote the output verbatim, with the error and exit status, and name the
     architecture, version, or environment it came from.
   - **read**: you traced it in code or docs. Cite `path:line` or the URL, and the commit when the age
     of the code matters.
   - **agreed**: the humans in the conversation decided it. Say so, and keep it in their terms.
   - **inferred**: you think so. Say "likely", and say what would settle it.

   A bug found mid-work needs one extra thing: **whether it is pre-existing or self-inflicted**, shown
   rather than asserted. Three independent checks make it solid:
   ```bash
   git log -1 --format='%h %cs' -- <path>       # how old is the code
   git diff origin/main...HEAD -- <path>        # does the current work touch it at all
   git stash && <build+repro> && git stash pop  # does the base commit reproduce it
   ```

6. **Write the description.** Four parts are universal, whatever the kind:
   - **Opening**: where this came from, then the ask in two or three sentences. When a reviewer, a
     customer, or a teammate raised it, say who and link it.
   - **Why it matters**: the consequence or the payoff, worst or biggest first. Name the workload,
     customer, or person affected. If you cannot state this in one sentence, you do not understand the
     ask well enough to file it yet.
   - **`## Done when`**: how anyone can tell it is finished. For a bug, the behaviour that replaces the
     failure. For a feature, the observable capability. For a spike, the question answered and where the
     answer gets written down. Without this, only the author can ever close it.
   - **`## Scope`**: what is in, and what is deliberately out. Record what the conversation declined, or
     it gets proposed again.

   Then add only the sections the kind earns:

   | kind | add |
   |---|---|
   | Bug | `## Mechanism` (why it happens, in system terms, with the minimal evidence), `## Repro` (exact commands, every environment constraint, and what the failure looks like), and `## Pre-existing, not from <X>` when provenance is in question |
   | Improvement or feature | the user-visible behaviour or API sketch, and the alternative designs considered |
   | Chore | what forces it now, and what breaks if it waits |
   | Investigation | the question, the timebox, and what would count as an answer |
   | Docs | who is misled today, and the correct statement |
   | Follow-up | why it was safe to defer, and the commit or pull request that deferred it |

   Close with **`## Open questions`** when any remain, and **`## Directions worth trying`** when the
   approach is unsettled: options rather than a mandate, the one you would take, and what is unknown.
   This is where someone disagrees with you cheaply, before code exists.

   **Length follows the decision the reader has to make.** Something subtle in shared machinery earns
   the full shape; a small ask earns six lines, and padding it to fill the headings wastes the reader.
   **Inline up to roughly twenty lines of output; attach anything longer** (step 11).

   The four universal parts, at the length most issues deserve:

   > **Title**: `auth: session cookies survive a password reset`
   >
   > Raised by Priya in #support on 2026-08-19, from a customer report. Resetting a password leaves
   > existing sessions valid, so a user who resets because they believe they are compromised stays
   > compromised. Confirmed by reading `auth/session.go:212`: the reset writes the new hash and never
   > touches the session table.
   >
   > **Why it matters**: password reset is the control we tell customers to use after a leak, and today
   > it does not end the attacker's session.
   >
   > `## Done when` A reset invalidates every session for that user except the one performing it, and a
   > test asserts an old cookie is rejected afterwards.
   >
   > `## Scope` Password reset only. Deliberately out: invalidation on email change and on role change,
   > which Priya and I agreed are separate asks.

7. **Collect what the issue should link to.** An issue that names no sources makes the next person redo
   the work. Note in the draft which of these exist:
   - the **pull request** that fixes it, contains the offending change, or was in flight when it came
     up, and the **commit** when there is no pull request
   - the **review comment, thread, or chat message** that raised it, and the person who raised it
   - the **CI run, dashboard, or job** that shows the failure
   - the **upstream source**: an upstream issue, a pinned source file at the version you read, the
     documentation that says what correct looks like
   - the **RFD, design doc, or spec** it is judged against
   - **sibling issues**, which go in relations rather than links (step 10)
   ```bash
   gh pr view <n> --json url,title --jq '"\(.url) \(.title)"'
   gh api repos/<owner>/<repo>/pulls/<n>/comments --jq '.[] | "\(.html_url) \(.user.login)"'
   gh run list --branch "$(git rev-parse --abbrev-ref HEAD)" --limit 3 --json url,conclusion
   ```

8. **Decide the fields, and take defaults from evidence rather than instinct.** Very little of this is
   usually written down, so know which is which and say so in the draft when it matters.
   - **assignee**: yourself when you are starting now, otherwise leave it empty. Never assign another
     person. Some repos mandate self-assign on start, which is what step 2 looks for. The field is
     `assignee` and accepts an id, name, email, or `"me"`.
   - **state**: the team's started state only when work begins now, otherwise its backlog or triage
     state. Names are per team, so take them from `list_issue_statuses`, not from memory.
   - **priority**: `0` none, `1` urgent, `2` high, `3` medium, `4` low. Match what siblings of the same
     kind and consequence carry. Leave it at none rather than inventing urgency.
   - **estimate**: the scale is per team, so read a sibling's number instead of guessing a unit. When
     the fix is unknown, estimate the investigation and say in the text that this is what it covers.
     Some teams disallow zero.
   - **project** and **parentId**: the project the work belongs to, and the epic it is part of. A
     sub-issue under the wrong parent is invisible.
   - **labels**: component, area, and kind are usually three separate labels. `labels` **replaces** the
     whole set, so pass all of them or omit the field.
   - **milestone**: this is a **Linear project milestone**, from `list_milestones` for that project, and
     it is unrelated to any GitHub milestone a pull request template may demand. Set it only when the
     project uses them.

9. **Draft it, and know whether you need permission.**
   - **The human asked for the issue** ("file an issue for X", "open a ticket for this"): the authority
     is already there. Show the draft as one message in the conversation and file it. Write a file first
     only when it is long enough that reviewing it in chat is awkward, or when a draft was asked for.
   - **You are proposing an issue nobody asked for**: write it to `thoughts/tickets/<slug>.md`, or
     wherever the repo keeps such notes, show the title, the fields, the search table, the links, and
     the description, and **stop**. Wait for an explicit "file it". Silence is not consent, and neither
     is a question about something else.

10. **File it.** Search the exact title once more first, since a retried run after a failed call is how
    two identical issues appear.
    ```
    list_issues({query: "<exact title>", fields: ["title","url"]})
    save_issue({
      title, team, project, parentId, assignee, state, priority, estimate, labels, milestone,
      relatedTo: [...], blockedBy: [...], blocks: [...],  // append-only; removeRelatedTo undoes
      links: [{url, title}, ...],                          // everything from step 7
      description,
    })
    ```
    Title as `component: what is wrong or what should exist`, stated as a fact or an outcome rather
    than a task, and recognisable in a list of eighty. Use `blocks` and `blockedBy` where one issue
    genuinely gates another instead of writing "blocked by X" in prose: the graph shows up in triage,
    prose does not.

11. **Attach the material that is a file rather than a URL**, such as a captured log, a report, or a
    screenshot: `prepare_attachment_upload`, PUT the bytes, then `create_attachment_from_upload`. Scrub
    it first.

    When a pull request is involved, close the loop from its side too: use Linear's **Copy git branch
    name** (`gitBranchName`) when the branch does not exist yet, and when it already exists under
    another name, add `Closes ARCH-1234` to the pull request body and tick the template's Linear
    checkbox, which is now true. Do not rename a pushed branch to chase the convention.

12. **Updating an existing issue.** Prefer a **comment** for a new observation, a measurement, or
    anything with a timestamp to it, and a **description patch** for what should be true for every
    future reader. Do not rewrite a description to argue with its earlier version; make it read as a
    standalone statement of the current state.
    ```
    get_issue({id: "ARCH-1234"})                       // always read the stored text first
    list_comments({...})                               // and the thread, so you do not repeat it
    save_issue({id: "ARCH-1234", patch: [{op: "replace", old_string, new_string}]})
    save_issue({id: "ARCH-1234", state: "In Review", links: [{url, title}]})
    save_comment({issueId: "ARCH-1234", body: "..."})  // body plus exactly one parent id
    ```
    Patch anchors must match the **stored** text, which is not what you typed. See Gotchas.

13. **Verify what landed, not what you sent**, then fix what it made stale. `get_issue` and check
    parent, project, labels, estimate, assignee, milestone, links, and that relations appear on **both**
    sides. Re-read the rendered description. If a sibling ticket now credits this work to "the
    such-and-such branch", patch it to name the issue instead: pointing at a branch that disappears on
    merge ages badly.

## Guidelines

- **Carry the conversation faithfully.** Attribute decisions to whoever made them, keep a customer's or
  reviewer's words as theirs, and do not launder your own suggestion into a settled conclusion.
- **Link generously.** Every issue should carry the pull request, commit, review thread, CI run, or
  source it came from. A reader who has to reconstruct where this came from is paying for your saved
  keystroke.
- **No em dashes.** Rewrite the clause; do not swap in an en dash or a spaced hyphen.
- Write the **current state, standalone**. An issue is not a reply to an earlier draft of itself, and a
  reader arriving in three months has no memory of this session.
- **Absolute dates**: `2026-08-18`, never "yesterday". Same for versions and commits: name them.
- Type `ARCH-1234` as plain text. Linear linkifies it, so hand-written markdown links are noise.
- One ask per issue. If it is two pull requests, it is two issues.
- Reading is free, writing is not. `get_issue` and `list_issues` freely; every `save_issue` is visible
  to the team.

**Never**:

- paste secrets, credentials, tokens, or customer data, including inside logs and screenshots
- assign the issue to another person, or set a cycle you were not asked to set
- invent a priority or an estimate to fill the field; take them from siblings or leave them unset
- reference the issue id in a source comment. Relations and the pull request description carry that
- use the issue as a live scratchpad. That is what `thoughts/` is for, and an issue edited nine times in
  an hour is unreadable
- file while the thing is still moving. Wait until it stops changing, then file once

## Gotchas

Each of these cost real time once.

- **`patch` anchors match the stored text, not what you typed.** Linear rewrites `ARCH-1300` into
  `<issue id="uuid" href="...">ARCH-1300</issue>`, so a patch anchored on the bare id fails with
  "old_string not found". Anchor on prose containing no issue reference, or use `replace_range` with
  `from`/`to` either side of the tag. One failed operation aborts the whole patch.
- **Every anchor must match exactly once.** Boilerplate phrases are not anchors.
- **Read the result when patching prose.** Substituting an issue reference into "the X branch's fix"
  yields "ARCH-1335's branch's fix". The patch succeeds and the sentence is wrong.
- **`labels` is a replace, not an add.** Passing one label silently drops the others.
- **An issue filed for your own in-flight work still needs its state set.** Left in the backlog with a
  pull request open, it reads as unstarted to everyone else.

Common write failures and their fix:

| failure | cause | fix |
|---|---|---|
| unknown state | state names are per team | `list_issue_statuses` for that team |
| label rejected | label belongs to another team | `list_issue_labels` for this team |
| estimate rejected | different scale, or zero disallowed | copy a sibling's estimate |
| parent rejected | parent is in another team | pick a parent in the same team |
| milestone rejected | milestones belong to a project | `list_milestones` for that project |
| assignee ignored | `assigneeId` is not a field | use `assignee` with an id, name, email, or `"me"` |
