---
name: weekly-report
description: Generate a weekly progress report from git commits, PRs, review activity, Linear tickets and Slack activity, then update the team's Slite standup doc. Use when asked for a weekly report, a standup update, or a summary of what shipped. Writes to Slite, so only on an explicit request.
argument-hint: [author-name]
allowed-tools: Bash(git *), Bash(gh *), mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__list_comments, mcp__claude_ai_Linear__get_user, mcp__claude_ai_Linear__get_issue, mcp__slack__slack_search_public_and_private, mcp__slack__slack_search_users, mcp__slack__slack_read_thread, mcp__slite__search-notes, mcp__slite__get-note, mcp__slite__get-note-children, mcp__slite__modify-range, mcp__slite__append-blocks, mcp__slite__remove-blocks
---

Generate a weekly progress report for the specified author (default: current git user), then update the team's Slite standup doc with the report.

> Most of the MCP tools below (Linear, Slack, Slite) are deferred — load their schemas with `ToolSearch` (e.g. `select:mcp__claude_ai_Linear__list_issues,...`) before calling them. The Linear server is `claude_ai_Linear`, not `linear`. Run independent gathering calls in parallel.
>
> **If an MCP server is broken or won't connect, STOP and ask the user to fix it — do not work around it.** Each of these servers is load-bearing: Linear for ticket activity, Slack for uncaptured work, Slite for the doc update. If a server is still "connecting", `ToolSearch` again to give it a moment; if it then errors, fails to authenticate, or its tools keep erroring, pause and tell the user exactly which server is down and what to do (e.g. "the claude.ai Linear MCP isn't connected — run `/mcp` to authenticate, then tell me to continue"). Resume only once they confirm it's fixed. Do not silently fall back to inferring data (e.g. guessing ticket IDs from branch names) — that produces a degraded report.

## Steps

1. **Gather git commits from the past week**
   ```bash
   git config user.name  # Get default author if not specified
   git log --oneline --since="7 days ago" --author="$ARGUMENTS" --all | head -50
   ```

2. **List recent PRs (open and merged)**
   ```bash
   gh pr list --author @me --state all --limit 20
   gh pr list --author @me --state open --json number,title,url,createdAt
   gh pr list --author @me --state merged --limit 20 --json title,number,mergedAt,url
   ```
   Only count PRs merged within the report window (the last 7 days) — `gh` returns more than that.

3. **Get detailed PR information**
   - For each open PR, get commit messages, file counts, and line changes
   ```bash
   gh pr view {number} --json commits,files,additions,deletions,body
   gh pr view {number} --json commits --jq '.commits[].messageHeadline'
   ```
   - Check who approved/reviewed your open PRs (worth noting "approved, ready to merge"):
   ```bash
   gh api "repos/{owner}/{repo}/pulls/{number}/reviews" --jq '.[] | "\(.user.login): \(.state)"'
   ```

4. **Check submodules for contributions**
   ```bash
   git submodule foreach 'git log --oneline --since="7 days ago" --author="$ARGUMENTS" | head -20'
   ```
   For each submodule with commits, get detailed commit info:
   ```bash
   cd {submodule_path} && git log --oneline -10 --format="%h %s (%an, %ad)" --date=short
   ```

5. **Gather Linear ticket activity from the past week**
   - Issues assigned to you, updated in the past week (catches status/column moves):
     `mcp__claude_ai_Linear__list_issues` with `assignee="me"`, `updatedAt="-P7D"`, `limit=50`
   - Issues you created in the past week:
     `mcp__claude_ai_Linear__list_issues` with `assignee="me"`, `createdAt="-P7D"`, `limit=50`
   - For any ticket you reference in THIS WEEK whose title/status you don't already have, fetch it:
     `mcp__claude_ai_Linear__get_issue` with `id="ARCH-XXX"` (gives exact title, status, milestone, branch name)
   - Note the `status` and `completedAt`/`startedAt`/`createdAt` fields to infer transitions (e.g. Created → In Review, In Progress → Done). Correlate each ticket to its PR via the matching branch name.

6. **Check Slack for work not captured in git/Linear** (this is where customer debugging, support, and ad-hoc help surface)
   - Find your messages across all channels/DMs for the window (the logged-in Slack user_id is reported in the tool description; use it as `from:`):
     `mcp__slack__slack_search_public_and_private` with `query="from:<@USER_ID> after:YYYY-MM-DD"`, `sort="timestamp"`, `sort_dir="desc"`, `include_context=false`, `limit=20`. Page through with the returned cursor to cover the whole week.
   - Triage the results:
     - **Keep** work the git/Linear/PR pass missed — e.g. live customer debugging, root-causing an issue with a customer, shipping a custom build, writing diagnostic/helm/migration instructions, cross-team unblocking. These are real accomplishments that leave no PR.
     - **Drop** non-work chatter (#random, #yelling, #non-tech, etc.) and anything already represented by a PR/ticket.
   - Use `mcp__slack__slack_read_thread` to pull context on a notable thread (e.g. the customer thread that spawned the week's tickets) so the bullet is accurate.
   - Add a LAST WEEK bullet for each genuine gap found, then tell the user what you found vs. what was already covered vs. what you excluded.

7. **Format the report using this template**

   Output the report wrapped in a markdown code block for review:

   ````
   ```markdown
   ### [Author Name]

   - **LAST WEEK**
       - [Main accomplishment] ([ARCH-XXX](linear-url), [PR #X](github-url)[, status/size])
           - [Sub-detail if relevant]
       - [Customer / support / debugging work that left no PR — from Slack]
   - **THIS WEEK**
       - [Planned item] ([ARCH-XXX](url), [#X](url) — status)
   - **GITHUB**
       - [PR #X: Title](url) - Open/Merged[, approved]
   - **LINEAR**
       - [ARCH-XXX: Title](url) - [Old] → [New] (PR #X)
   ```
   ````

8. **Update the team's Slite standup doc**
   - The doc lives under the **Meeting Notes** collection (note id `CI3DMW9Bbd62ZD`) and is titled `Updates - <Month DD, YYYY>` for the current week (standups are Mondays). Find it with `mcp__slite__search-notes` (query `"Updates <Month DD YYYY>"`) or `mcp__slite__get-note-children` on `CI3DMW9Bbd62ZD`.
   - `mcp__slite__get-note` with `format="sliteml"` to read it and get block IDs. Your section is under `## Team Updates`, heading `### [Author Name]`.
   - **The section usually still holds last cycle's content carried over** — verify the ticket/PR numbers; if they're from the previous week, replace the whole section body.
   - Replace the stale section body (from the first `**LAST WEEK**` block through the last `**LINEAR**` item) with `mcp__slite__modify-range` (`startBlockId`/`endBlockId` = those two blocks). To add a few bullets without rewriting, use `mcp__slite__append-blocks` with `afterBlockId`. To drop bullets, use `mcp__slite__remove-blocks`.
   - **Match the doc's existing format**, not generic markdown: links are `<a url="https://...">text</a>` (not `[text](url)`), bullets nest with 2 spaces per level, escape `&` as `&amp;` and `"` as `&quot;`.
   - **Depth gotcha:** `append-blocks` auto-anchors new bullets to the depth of the block they follow, so a second appended bullet can nest under the first. Fix by replacing the run with `modify-range` anchored on a correct-depth sibling, or set `<li depth="N">` explicitly. Verify the returned `changedContent` shows the right nesting.
   - Leave every other person's section and the Company Updates / Guidelines sections untouched.

## Guidelines

- Group related commits into logical accomplishments (don't list every commit).
- **Do not include reviews you gave** to others' PRs — leave them out of LAST WEEK and GITHUB. (Noting that one of *your* PRs was approved/ready-to-merge is fine.)
- For "THIS WEEK", infer from open PRs, Linear tickets in progress/todo, and any items the user calls out. Include ticket links + status.
- Include submodule contributions as separate line items.
- Keep bullets concise but informative; link PRs and tickets.
- For Linear tickets: include ones you created, ones whose status changed (show transitions like "In Progress → Done"), and correlate to PRs via branch name.
- Surface the Slack-only work prominently — it's the highest-value thing this skill recovers, since it's invisible to git and often the week's hardest work.
- After updating Slite, summarize for the user: what the report covers, what Slack surfaced, and confirm no other sections were touched.
