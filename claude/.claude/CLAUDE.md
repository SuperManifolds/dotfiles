# Global Instructions

## Communication

- Be concise and technical. Lead with the answer, then a short rationale.
- Cite sources for nontrivial facts. If uncertain, state assumptions explicitly.
- Avoid fluff, hype, and anthropomorphism.
- If multiple interpretations exist, present them — don't pick silently.
- Ask clarifying questions if a key spec is missing that blocks correctness.

## Surgical Changes

- Touch only what the task requires. Don't "improve" adjacent code, comments, or formatting.
- Match existing style, even if you'd do it differently.
- Remove imports/variables/functions that your changes made unused.
- Don't remove pre-existing dead code unless asked — mention it instead.

## Code Quality

- Address all warnings (linters, compilers). Never silence without explicit consent.
- Remove dead code — don't comment it out or suppress with attributes.
- Prefer early returns over deep nesting. Keep functions small and single-purpose.
- Use constants for magic numbers, colors, and spacing values.
- Prefer declarative/functional patterns over imperative loops.

## Testing

- Use the project's test runner, not the raw tool.
- Never skip tests — a skipped test is a broken test.
- Isolate state per test.
- Document suspected bugs without fixing implementation unless asked.

## Error Handling

- Validate inputs at system boundaries.
- Use the language's idiomatic error types — don't swallow errors silently.
- Provide context in error messages.

## Execution

- For multi-step tasks, state a brief plan with verifiable checks before starting.
- Transform vague requests into concrete goals (e.g. "fix the bug" → "write a test that reproduces it, then make it pass").
- IMPORTANT: After making changes, run the relevant build/test/lint command to verify. Show evidence of success rather than asserting it worked.

## Don'ts

- IMPORTANT: Never commit secrets, API keys, or credentials.
- Never add dependencies without asking first.
- Never run the full test suite when a specific test file can be targeted.
- Never generate mock data with obviously fake values ("test123", "foo@bar.com") — use realistic values.

## Git

- Use conventional commit style (e.g. `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`).
- Don't amend published commits.
