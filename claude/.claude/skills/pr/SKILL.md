---
name: pr
description: Create a pull request with a well-structured description, using the repo's PR template if one exists. Use when asked to open, create, or raise a PR, or to write a PR description. Creates GitHub state, so only on an explicit request.
argument-hint: [base-branch]
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

Create a pull request from the current branch. If `$ARGUMENTS` is provided, use it as the base branch; otherwise default to the repo's default branch (`gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'`, falling back to `main`).

## Steps

1. **Understand the current branch state**
   Run these in parallel (substitute the resolved base branch for `<base>`):
   ```bash
   git log origin/<base>...HEAD --oneline   # all commits on this branch
   git diff origin/<base>...HEAD --stat      # files changed summary
   git diff origin/<base>...HEAD             # full diff for reference
   ```

2. **Find any linked issue or ticket**
   - Look for an issue/ticket reference in the branch name or commit messages — e.g. a GitHub issue number (`#123`) or a tracker key like `ABC-456` (`arch-796` from `feature/arch-796-shadow-ports`).
   - If one is found and you have a tool that can fetch it (e.g. `gh issue view <n>`, or an issue-tracker MCP server if one is connected), fetch its title and description for context.
   - Remember the reference so you can add a closing line later. If no issue is linked, skip the closing line entirely — don't invent one.

3. **Read the PR template if the repo has one**
   - Find it with one command that cannot produce a false negative:
     ```bash
     find . -maxdepth 3 -iname "*pull_request_template*" -not -path "./node_modules/*"
     ```
     This covers `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, files under
     `.github/PULL_REQUEST_TEMPLATE/`, `docs/`, and the repo root, and it is case-insensitive.
   - **Do not probe with a bare glob** (`ls .github/PULL_REQUEST_TEMPLATE*`). Under zsh an unmatched
     glob fails the whole command before `ls` runs, so an `|| echo "(none)"` fallback reports "no
     template" for a repo that has one. That failure mode is silent and it has happened.
   - If nothing is found, confirm it by listing the directory itself (`ls -a .github/`) before
     concluding the repo has no template.
   - A template is usually a **checklist** rather than prose sections. Check whether the convention
     is to keep it: `gh pr view <recent-merged-pr> --json body --jq '.body' | grep -c "^- \[[ x]\]"`
     on two or three recent merged PRs. If they keep it, your body must include it too, with the
     prose and sections from step 6 added around it.
   - If a template exists, follow its structure and checklist. If none exists, use the default
     structure in step 6.
   - Read what the checklist actually demands. Items like "at least one label" and "milestone
     assigned" are requirements on the PR, not just boxes: satisfy them in steps 8 and 10 rather
     than ticking them blind.

4. **Read key files that were changed** to understand what the code actually does — don't just rely on commit messages.

5. **Match the repo's PR description style**
   - Look at a few recent merged PRs to mirror the project's conventions: `gh pr list --state merged --limit 3 --json number,title,body`.
   - If the repo has an obvious house style (headers, section names, level of detail), follow it over the default below.

6. **Write the PR description**

   If the repo has a PR template (step 3), use it as the base structure and fill in its sections. Otherwise, use this default structure:

   - **Opening prose**: 1-3 paragraphs explaining what this PR accomplishes and how, in plain language. No headers, no bullet points — just clear prose that someone unfamiliar with the codebase could follow. Include usage examples (annotation format, config snippets, CLI invocations) inline with code blocks where relevant.

   - **`### Changes` section**: List each new or meaningfully changed component/directory with a short description. Group related changes logically — don't list every single file. Format:
     ```
     ### Changes
     - path/to/component/ — What was changed or added here
     - path/to/other/ — Description of changes
     ```

   - **`### Tests` section**: List each new or changed test with a short description of what it verifies (what it proves, not just its name). Format:
     ```
     ### Tests
     - Test name or category — What it verifies and how
     ```

   - **`### How to test` section**: Concrete commands or steps a reviewer can use to verify the changes. Format:
     ```
     ### How to test
     - Step or command to verify the changes
     ```

   If step 2 found a linked issue, end the body with a closing line in the syntax the host supports — `Closes #123` for a GitHub issue, or the tracker's convention (e.g. `Closes ABC-456`) if it integrates with the repo. Omit this line if no issue was linked.

   **Do NOT include**: a `## Summary` header or bullet-point summaries at the top (the opening prose covers this), or sections the repo's template/style doesn't call for.

   If you used a template with a checklist, check the boxes this PR fulfills (descriptive title, targets the right base, description present, how-to-test provided) and leave the rest unchecked. Don't check items an author must confirm manually (e.g. before/after comparisons, manual QA).

7. **Set the PR title** using the repo's convention — conventional-commit format with a component scope where the repo uses one, e.g. `feat(networking): add shadow port DNAT`. Otherwise a short imperative subject.

8. **Determine labels and milestone** from the areas of the codebase changed.
   - List the full set before deciding: `gh label list --limit 100 --json name --jq '[.[].name] | join(" ")'`.
     A default `gh label list` truncates, and a component label (`cruise`, `console.v2`) can sit past
     the cut, which reads as "no matching label" when one exists.
   - The strongest signal is what comparable merged PRs used:
     `gh pr list --state merged --limit 5 --search "<component> in:title" --json number,labels,milestone`.
     Mirror those.
   - Apply only labels that exist. Skip labeling only if the repo genuinely has none, and note that
     many repos generate release notes from labels, so "no label" is usually wrong rather than neutral.
   - If merged PRs carry a milestone, set the same one (`--milestone "<title>"`); check the open list
     with `gh api repos/<owner>/<repo>/milestones --jq '.[].title'`.

9. **Get the current GitHub username** for assignment:
   ```bash
   gh api user --jq '.login'
   ```

10. **Create the PR as a draft**
    ```bash
    gh pr create \
      --base "<base>" \
      --draft \
      --assignee "<your-username>" \
      --label "label1,label2" \
      --milestone "<milestone-title>" \
      --title "..." \
      --body "$(cat <<'EOF'
    ...
    EOF
    )"
    ```

    Omit `--label` / `--milestone` only when the repo uses neither. Do NOT assign reviewers — the author will do this when ready.

11. **Verify what actually landed**, since a body assembled in a heredoc can lose sections and a
    silent probe failure can lose the template:
    ```bash
    gh pr view <n> --json body,labels,milestone,isDraft,assignees
    ```
    Confirm the template checklist is present if the repo keeps one, the sections you intended are
    there, and the label and milestone are set. Fix with `gh pr edit <n> --body-file …` rather than
    describing the body you meant to write.

12. Return the PR URL when done.

## Guidelines

- The description should be detailed enough that a reviewer understands the full scope without reading every file.
- Group related changes logically — don't enumerate every file.
- For tests, describe what each one proves, not just its name.
- Keep prose concise but complete — no fluff, no filler.
- Do not add Claude Code attribution to the PR description.
- Always create as a draft PR and assign the current user.
- Respect the repo's PR template and checklist over these defaults when they conflict.
