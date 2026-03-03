---
name: pr
description: Create a pull request with a well-structured description
disable-model-invocation: true
argument-hint: [base-branch]
allowed-tools: Bash(git *), Bash(gh *), Read, Grep, Glob
---

Create a pull request from the current branch. If `$ARGUMENTS` is provided, use it as the base branch; otherwise default to `main`.

## Steps

1. **Understand the current branch state**
   ```bash
   git log origin/$ARGUMENTS...HEAD --oneline   # all commits on this branch
   git diff origin/$ARGUMENTS...HEAD --stat      # files changed summary
   ```

2. **Find the relevant Linear ticket**
   - Extract the ticket ID from the branch name (e.g., `arch-796` from `supermanifolds/arch-796-shadow-ports-...`)
   - Use the Linear MCP tools to fetch the ticket title and description for context

3. **Read key files that were changed** to understand what the code actually does — don't just rely on commit messages

4. **Write the PR description** in this style:

   - **Opening prose**: 1-3 paragraphs explaining the problem and the solution in plain language. No headers, no bullet points — just clear prose that someone unfamiliar with the codebase could follow. Include usage examples (e.g., annotation format, config snippets) inline with code blocks where relevant.

   - **`### Components:` section**: List each component/directory that was meaningfully changed with a short description of what was added or modified. Format:
     ```
     ### Components:
     - path/to/component/ — What was changed or added here
     - path/to/other/ — Description of changes
     ```

   - **`### Tests` section**: List each test with a short description of what it verifies. Format:
     ```
     ### Tests
     - Test name or category — What it verifies and how
     - Another test — Description
     ```

   - **`### How to test` section**: Provide concrete commands or steps a reviewer can use to verify the changes. This might include running specific tests, deploying to a dev cluster, or manual verification steps. Format:
     ```
     ### How to test
     - Step or command to verify the changes
     - Another verification step
     ```

   **Do NOT include**: a `## Summary` header, bullet-point summaries at the top, or any other sections beyond the four above.

5. **Set the PR title** to match the main commit's conventional commit format (e.g., `feat(kubernetes): add shadow port DNAT...`)

6. **Create the PR**
   ```bash
   gh pr create --title "..." --body "$(cat <<'EOF'
   ...
   EOF
   )"
   ```

7. Return the PR URL when done.

## Guidelines

- The description should be detailed enough that a reviewer understands the full scope without reading every file
- Group related changes logically in the Components section — don't list every single file
- For the Tests section, describe what each test proves, not just its name
- Keep prose concise but complete — no fluff, no filler
- Do not add Claude Code attribution to the PR description
