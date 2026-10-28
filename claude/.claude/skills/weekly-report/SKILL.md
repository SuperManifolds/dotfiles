---
name: weekly-report
description: Generate the Friday end-of-week update for the Virtualization team from git commits, PRs, Linear tickets, Slack activity and Notion meeting notes, then write it into the author's section of the team's weekly reflections page in Notion once the user approves the draft. Use when asked for a weekly report, an end-of-week update, a Friday reflection, or a summary of what shipped. Drafts first and never writes without explicit approval.
argument-hint: [author-name]
allowed-tools: Bash(git *), Bash(gh *), mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__list_comments, mcp__claude_ai_Linear__get_user, mcp__claude_ai_Linear__get_issue, mcp__slack__slack_search_public_and_private, mcp__slack__slack_search_users, mcp__slack__slack_read_channel, mcp__slack__slack_read_thread, mcp__claude_ai_Notion__notion-query-meeting-notes, mcp__claude_ai_Notion__notion-query-data-sources, mcp__claude_ai_Notion__notion-fetch, mcp__claude_ai_Notion__notion-update-page, mcp__claude_ai_Notion__notion-ai-search
---

Generate the author's end-of-week update (default author: current git user), show it for review, and write it to the weekly reflections page in Notion only after the user approves it.

## Context

The Virtualization team at LiveKit. Work is visible in three places and the update has to reconcile all three:

- **Notion** is where the update goes: the **Weekly reflections** database (`https://app.notion.com/p/052a1e17721245a9a828a42aedd11e73`, data source `collection://09af107c-8094-48ca-9718-1f8178f1e793`) under Agent Platform Home / Virtualization Team. A Notion automation creates one page per week named `Week of <Month D, YYYY>` (the Monday), with a `Week` date property, and posts a reminder in `#team-virtualization` on Fridays. Each person owns an `## <First name>` section; the page also has team-level `### Decisions` and `### Risks` sections.
- **Slack** is a source, not the destination: blockers and cross-team work live in `#team-virtualization` (`C0C2GH5NBN1`) and DMs.
- **Linear** lives at `linear.app/livekit`, team **VIRT**. Older tickets carry the `ARCH-` prefix from before the acquisition; quote those as written when they appear in a PR title, but reference new work as `VIRT-NNN`.
- **Notion** also holds meeting notes and RFDs, including the action items assigned to the author in the team syncs.

The main repo is `github.com/livekit/virtualization` (formerly `loopholelabs/theseus`); still resolve it with `gh repo view --json nameWithOwner` from the working tree rather than hardcoding it. Team members also work in `agx-runtime/substrate`, `agx-runtime/lkhead`, `livekit/substrate-runtime`, `livekit/substrate-kernels` and `livekit/cloud-config`; if the author has commits there in the window, they belong in the update.

**The ritual:** the Friday meeting is replaced by an async weekly reflection, written when each person wraps up their week (agreed 2026-09-25 as a Slack post, moved to the Notion page from the week of 2026-10-05). Monday is planning. The point of the reflection is the context that PRs and Linear do not carry, so **blockers and asks are the highest-value part**, not an afterthought.

**The page is team-visible. Nothing from a 1:1 goes in it.** A 1:1 meeting note (two attendees, titled like `Shiv / Alex Weekly Sync`) is private: do not quote it, paraphrase it, or use its action items or discussion as a source for any item, even one that seems harmless. Read group meeting notes only for commitments.

> Linear, Slack and Notion tools are deferred, so load their schemas with `ToolSearch` (e.g. `select:mcp__claude_ai_Linear__list_issues,...`) before calling them. The Linear server is `claude_ai_Linear`; the Slack server is `slack`; the Notion server is `claude_ai_Notion`. Run independent gathering calls in parallel.
>
> **If an MCP server is broken or won't connect, STOP and ask the user to fix it rather than working around it.** Each is load-bearing: Linear for ticket activity, Slack for uncaptured work, Notion for meeting commitments and for writing the reflection. If a server is still "connecting", `ToolSearch` again to give it a moment; if it then errors or fails to authenticate, pause and tell the user exactly which server is down and what to do (e.g. "the claude.ai Linear MCP isn't connected, run `/mcp` to authenticate then tell me to continue"). Do not silently fall back to inferring data, such as guessing ticket IDs from branch names; that produces a degraded report.

## Steps

1. **Establish the author and the window**
   ```bash
   git config user.name          # default author if none given
   gh repo view --json nameWithOwner
   ```
   The window is the working week being reflected on, normally Monday through the Friday you are posting. State the dates you used.

2. **Gather git commits**
   ```bash
   git log --oneline --since="7 days ago" --author="$ARGUMENTS" --all | head -50
   ```
   Run this in each repo the author worked in, not just the current one.

3. **List PRs, open and merged**
   ```bash
   gh search prs --repo <owner/name> --author @me --state open --json number,title,url,createdAt,isDraft
   gh search prs --repo <owner/name> --author @me --merged --json number,title,url,closedAt
   ```
   Both passes use `gh search prs`. `gh pr list --author @me` returns an empty array here even when the author has open and merged PRs, so a run built on it silently reports no open work. A draft PR still counts: it is where the week's unlanded work lives.

4. **Get the detail that makes a bullet worth reading**
   ```bash
   gh pr view {number} --json commits,files,additions,deletions,body
   gh api "repos/{owner}/{repo}/pulls/{number}/reviews" --jq '.[] | "\(.user.login): \(.state)"'
   ```
   An open PR that is approved and waiting is an ask, not a status line. Put it under blockers.

5. **Gather Linear activity**
   - Assigned to you and updated in the window, which catches status moves:
     `mcp__claude_ai_Linear__list_issues` with `assignee="me"`, `updatedAt="-P7D"`, `limit=50`
   - Created by you in the window:
     `mcp__claude_ai_Linear__list_issues` with `assignee="me"`, `createdAt="-P7D"`, `limit=50`
   - For any ticket you name whose exact title or status you don't have:
     `mcp__claude_ai_Linear__get_issue` with `id="VIRT-NNN"`
   - Read `status`, `completedAt`, `startedAt` to infer transitions, and correlate each ticket to its PR through the branch name.
   - In `fields`, the ticket key is `id`, not `identifier`. Passing `identifier` fails validation and costs a round trip.

6. **Read the comments on every ticket you are going to mention**
   `mcp__claude_ai_Linear__list_comments` with `issueId="VIRT-NNN"`, ordered by `createdAt`.

   This is where the week's real context lives, and it is the step most likely to be skipped. A ticket that shows only "Todo to In Progress" in its state history often has a comment underneath explaining that the author read the thing, found it did not apply, and asked someone whether it is worth doing. That comment is the update, and the state change is not.

   When the author's own comment already poses the question, link it and quote its substance rather than rephrasing the question in Slack. It is a standing ask on the record, and pointing at it tells the reader it has been waiting since a specific date.

7. **Check Slack for work that left no PR**
   - Your messages across the window (the logged-in Slack user id appears in the tool description; use it as `from:`):
     `mcp__slack__slack_search_public_and_private` with `filters="from:<@USER_ID> after:YYYY-MM-DD"`, `sort="timestamp"`, `sort_dir="desc"`, `include_context=false`, `limit=20`. Page through the cursor to cover the whole week.
   - **Keep** what the git/Linear/PR passes missed: live debugging, unblocking another team, a custom build, design work argued out in a thread, an incident. These are real and invisible everywhere else.
   - **Drop** chatter and anything a PR or ticket already represents.
   - `mcp__slack__slack_read_thread` on a notable thread so the bullet is accurate rather than approximate.

8. **Check Notion for commitments you made**
   `mcp__claude_ai_Notion__notion-query-meeting-notes` filtered to the window, then `notion-fetch` the group sync notes and read the action items. Skip 1:1 notes entirely (see the privacy rule above). Anything assigned to the author that is still open is unfinished business and belongs in the body, said plainly as still owed and from when; anything done belongs in the body too.

9. **Find this week's page**
   Query the Weekly reflections data source for the row whose `Week` start is the window's Monday (or fetch the page linked from the Friday reminder in `#team-virtualization`), then `notion-fetch` it.
   - Read the callout at the top: it is the page's own instructions and wins over this skill where they differ.
   - Read the teammates' sections and the Decisions and Risks sections before drafting. Match their granularity, and do not restate what a teammate already covered about shared work.
   - Copy the author's section exactly as it stands (usually the empty template). Step 13 replaces that exact text, so it must match byte for byte.
   - If no page exists for the week, stop and tell the user; do not create one, because the automation owns that.

10. **Draft the update**

   Fill the template's five labels, in Notion-flavored markdown (tab-indented sub-bullets, `[text](url)` links, no emoji headers). Per the page's callout, **start every item with its Linear issue and link the PR**; work with no ticket starts `No Linear issue:`, as teammates write it.

   ````
   ```markdown
   ## Alex
   - **Shipped:**
   	- [VIRT-195](url): [#1233](url) Give a mid-handshake socket its dial target back under gVisor
   - **In progress:**
   	- [VIRT-NNN](url): [#NNNN](url) What it does for the system, then the evidence (draft)
   		- A sub-bullet for a finding worth its own line
   	- No Linear issue: [#NNNN](url) What it does
   - **Blocked on, or need from someone:**
   	- What you need, from whom, and what it unblocks
   - **Reviews:**
   	- [#1240](url) Warn when a refreshed variable read before the checkpoint has changed (Jimmy), approved
   - **Next week:**
   	- [VIRT-NNN](url): one line each
   ```
   ````

   Wrap filenames that look like domains (`run.sh`, `agent.py`) in backticks; Notion otherwise turns them into links to `http://run.sh`. Escape a leading `~` as `\~`.

   Keep every label even when empty, and write `None` under it rather than deleting it (the template is shared). **Next week** is part of the template, so fill it, briefly and only with things the author has actually said they will do; Monday's planning meeting still decides the order. Commitments the author still owes from a group meeting go in the body with the rest of the week, said plainly as still owed and from when.

11. **Run `fix-ai-speak` over the draft**
    Invoke the skill on the drafted post before showing it to anyone. This is not optional polish: the reflection goes out under the author's name on a page where their colleagues write their own, and the patterns the scanner finds are the ones that read as generated.

    Do not judge the draft by eye. Write it to a scratch file with a blank line between every bullet so each is scored as its own block, scan, edit, and scan again. Two habits this skill's output falls into every time: a `, so X` consequence clause in most bullets, and the whole section written in the third person when teammates write in the first. Report the deltas at the review gate, not an assurance.

    Keep the template's bold labels. They read as tier A tells in isolation, but they are the page's structure, and matching it beats a generic rule.

12. **Stop for review**

    Show the draft in a fenced block and state, in one line each: the Notion page it goes to (title and link), the date window, and anything you were unsure about. Then **stop and wait**.

    Do not call `mcp__claude_ai_Notion__notion-update-page` until the user has explicitly approved this specific draft. "Looks good", "post it", "send", "write it" are approval. Silence, a follow-up question, or an edit request are not. After any edit, show the revised draft and wait again.

13. **Write it, once approved**
    `notion-fetch` the page again first, because teammates edit it all week and the author's section may have changed since step 9. Then `mcp__claude_ai_Notion__notion-update-page` with `command="update_content"` and one `content_updates` entry: `old_str` is the author's current section from `## <Name>` up to (not including) the next `## ` heading, and `new_str` is the approved section. Touch nothing else on the page, including Decisions and Risks, unless the user asks. Fetch once more to confirm the nesting rendered, and return the page link.

## Guidelines

- Group commits into accomplishments. Nobody wants the commit log.
- **Include reviews you gave.** Review load is part of the week here, and every teammate's section lists it.
- Lead each bullet with what changed for the system, then the links. "Gave a mid-handshake socket its dial target back under gVisor" beats "modified inet.zig".
- Every claim carries its evidence: a PR link, a ticket link, or a commit. Anything you inferred rather than read, say so in the review step instead of smoothing it into a bullet. A URL you assembled from a pattern rather than read back from the API counts as inferred, so flag it.
- Blockers are the reason this post exists. An approved PR nobody merged, a review you have been waiting on, an environment you cannot get access to: name it, name who can clear it, and say what it holds up. A question the author already asked and nobody answered is a blocker, and the strongest form is a link to where it was asked and when.
- Answer the obvious objection in the same bullet. A headline number that moves a lot at the tail and barely at all at the median invites "so did it actually help", and one clause about why beats letting someone ask.
- Cross-repo work is one update, not several. Group by outcome, not by repository.
- No em dashes anywhere in the section.
- Keep it scannable. Each bullet one line where possible, and no preamble explaining what the post is.
- After writing, tell the user what the update covers, what Slack surfaced that git and Linear had missed, and give them the page link.
