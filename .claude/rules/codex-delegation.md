# Codex delegation policy

Use Codex as an independent, read-only reviewer rather than a second implementation agent.

## Mandatory consultations

- Before a multi-step implementation plan that changes an API contract, data model, dependency, or three or more related files.
- After an implementation is tested, before declaring a substantial task complete.
- When the same test failure remains after one focused repair attempt, or when the root cause is unclear.

## Do not consult

- Typos, formatting, straightforward one-file edits, or routine Git operations.
- When the user explicitly asks not to use Codex.
- When the task would require exposing secrets or sensitive data.

## Integration protocol

1. Run `powershell -File .claude/scripts/codex-consult.ps1 <mode> "<task statement>"` with the appropriate mode.
2. Read the report, validate important claims against the code and tests, then decide the action.
3. Do not copy a report into durable project documentation unchanged. Record only confirmed decisions.
4. Do not grant Codex write access in this template.
