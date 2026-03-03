---
name: weekly-report
description: Generate a weekly progress report based on git commits, PRs, review activity, and Linear tickets
disable-model-invocation: true
argument-hint: [author-name]
allowed-tools: Bash(git *), Bash(gh *), mcp__linear__list_issues, mcp__linear__list_comments, mcp__linear__get_user
---

Generate a weekly progress report for the specified author (default: current git user).

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

3. **Get detailed PR information**
   - For each open PR, get commit messages, file counts, and line changes
   ```bash
   gh pr view {number} --json commits,files,additions,deletions,body
   gh pr view {number} --json commits --jq '.commits[].messageHeadline'
   ```

4. **Check for reviews received on own PRs**
   ```bash
   gh api "repos/{owner}/{repo}/pulls/{number}/reviews" | jq -r '.[] | "Reviewed by \(.user.login): \(.state)"'
   ```

5. **Check for review comments made and received**
   - Get PR review comments (inline code comments)
   ```bash
   gh api "repos/{owner}/{repo}/pulls/{number}/comments" | jq -r '.[] | select(.user.login == "{author}") | "- \(.path | split("/") | last): \(.body | split("\n")[0][:70])"'
   ```
   - Get issue/PR comments (general discussion)
   ```bash
   gh api "repos/{owner}/{repo}/issues/{number}/comments" | jq -r '.[] | "\(.user.login) (\(.created_at | split("T")[0])): \(.body | split("\n")[0][:100])"'
   ```

6. **Check submodules for contributions**
   - Look for any submodules in the repo and check for commits there too
   ```bash
   git submodule foreach 'git log --oneline --since="7 days ago" --author="$ARGUMENTS" | head -20'
   ```
   - For each submodule with commits, get detailed commit info
   ```bash
   cd {submodule_path} && git log --oneline -10 --format="%h %s (%an, %ad)" --date=short
   cd {submodule_path} && git show {commit_hash} --stat | head -20
   ```

7. **Check for commit comments on submodule repositories**
   - Look for comments on commits in forked/submodule repos
   ```bash
   gh api "repos/{owner}/{submodule_repo}/commits/{commit_sha}/comments" | jq -r '.[] | "\(.user.login) (\(.created_at | split("T")[0])): \(.body | split("\n")[0][:80])"'
   ```

8. **Gather Linear ticket activity from the past week**
   - Get issues assigned to current user that were updated in the past week (includes moved/status changes)
   ```
   mcp__linear__list_issues with assignee="me", updatedAt="-P7D", limit=50
   ```
   - Get issues created by current user in the past week
   ```
   mcp__linear__list_issues with assignee="me", createdAt="-P7D", limit=50
   ```
   - For each issue found, check for comments to identify issues you commented on
   ```
   mcp__linear__list_comments with issueId for each relevant issue
   ```
   - Get current user info to filter comments by author
   ```
   mcp__linear__get_user with query="me"
   ```

9. **Format the report using this template**

   Output the final report wrapped in a markdown code block (triple backticks) for easy copy-paste:

   ````
   ```markdown
   ### [Author Name]

   - **LAST WEEK**
       - [Main accomplishment 1]
           - [Sub-detail if relevant]
       - [Main accomplishment 2]
       - [Review activity - PRs reviewed with key feedback given]
   - **THIS WEEK**
       - [Planned work item 1]
       - [Planned work item 2]
   - **GITHUB**
       - url - Status
       - url - Reviewed
   - **LINEAR**
       - url - Created/Moved to [Status]/Commented
       - url - Status change: [Old] → [New]
   ```
   ````

## Guidelines

- Group related commits into logical accomplishments (don't list every commit)
- Include review activity (both reviews given and received)
- For "THIS WEEK", infer from open PRs, Linear tickets in progress, and any TODO comments in recent commits
- Include contributions to submodules (like gVisor fork) as separate line items
- Link to PRs and issues where relevant
- Keep bullet points concise but informative
- For Linear tickets:
  - Include tickets you created in the past week
  - Include tickets where status changed (moved between columns/states)
  - Include tickets where you left comments
  - Show status transitions when relevant (e.g., "In Progress → Done")
  - Correlate Linear tickets with related PRs when possible
