---
name: pr
description: Create a pull request with a well-structured description using the repo's PR template
disable-model-invocation: true
argument-hint: [base-branch]
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

Create a pull request from the current branch. If `$ARGUMENTS` is provided, use it as the base branch; otherwise default to `main`.

## Steps

1. **Understand the current branch state**
   Run these in parallel:
   ```bash
   git log origin/<base>...HEAD --oneline   # all commits on this branch
   git diff origin/<base>...HEAD --stat      # files changed summary
   git diff origin/<base>...HEAD             # full diff for reference
   ```

2. **Find the relevant Linear ticket**
   - Extract the ticket ID from the branch name (e.g., `ARCH-796` from `supermanifolds/arch-796-shadow-ports-...`)
   - Use the Linear MCP tools to fetch the ticket title and description for context
   - Remember the ticket ID (e.g., `ARCH-796`) for the closing line

3. **Read the PR template**
   - Read `.github/pull_request_template.md` from the repository root
   - The template defines the checklist and structure to follow

4. **Read key files that were changed** to understand what the code actually does — don't just rely on commit messages

5. **Look at PR #400 for description style inspiration**
   ```bash
   gh pr view 400 --json body
   ```

6. **Write the PR description** using the repo's PR template as the base structure

   Replace the placeholder text at the top of the template with these sections:

   - **Opening prose**: 1-3 paragraphs explaining what this PR accomplishes and how, in plain language. No headers, no bullet points — just clear prose that someone unfamiliar with the codebase could follow. Include usage examples (e.g., annotation format, config snippets) inline with code blocks where relevant.

   - **`### Components:` section**: List each new or meaningfully changed component/directory with a short description. Format:
     ```
     ### Components:
     - path/to/component/ — What was changed or added here
     - path/to/other/ — Description of changes
     ```

   - **`### Tests` section**: List each new test with a short description of what it verifies. Format:
     ```
     ### Tests
     - Test name or category — What it verifies and how
     - Another test — Description
     ```

   - **`### How to test` section**: Provide concrete commands or steps a reviewer can use to verify the changes. Format:
     ```
     ### How to test
     - Step or command to verify the changes
     - Another verification step
     ```

   - **`### Before & After` section**: Add an empty comparison section for the author to fill in later. Format:
     ```
     ### Before & After
     - [ ] TODO: Add before & after comparison
     ```

   Keep the `---` separator and the `## ✅ Good Pull Request Checklist` section from the template intact below the description.

   **Check the checkboxes** in the checklist that are fulfilled by this PR (e.g., descriptive title, merges into main, short description, how to test). **Leave unchecked** any that are not fulfilled. Do NOT check the "Before & after comparison" checkbox — leave it for the author.

   End the entire body with:
   ```
   Closes ARCH-###
   ```
   (using the actual ticket ID extracted in step 2)

   **Do NOT include**: a `## Summary` header, bullet-point summaries at the top, or any sections beyond those specified above.

7. **Set the PR title** following the template's guidance: use conventional commit format with a project prefix, e.g. `feat(kubernetes): add shadow port DNAT...`

8. **Determine labels** by looking at what areas of the codebase were changed (e.g., `kubernetes`, `networking`, `experimental`). Check available labels:
   ```bash
   gh label list
   ```

9. **Get the current GitHub username**
   ```bash
   gh api user --jq '.login'
   ```

10. **Create the PR as a draft**
    ```bash
    gh pr create \
      --draft \
      --assignee "<your-username>" \
      --label "label1,label2" \
      --title "..." \
      --body "$(cat <<'EOF'
    ...
    EOF
    )"
    ```

    Do NOT assign reviewers — the author will do this when ready.

11. Return the PR URL when done.

## Guidelines

- The description should be detailed enough that a reviewer understands the full scope without reading every file
- Group related changes logically in the Components section — don't list every single file
- For the Tests section, describe what each test proves, not just its name
- Keep prose concise but complete — no fluff, no filler
- Do not add Claude Code attribution to the PR description
- Always create as a draft PR
- Always assign the current user
- The "Before & After" checkbox in the checklist must always be left unchecked
