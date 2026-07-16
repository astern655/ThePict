---
name: codex-consult
description: Consult Codex CLI as a read-only independent reviewer for substantial plans, unclear test failures, and final implementation reviews.
---

# Codex consultation

Use this skill only when the delegation policy in `.claude/rules/codex-delegation.md` requires a consultation.

## Procedure

1. Choose exactly one mode: `plan-review`, `failure-analysis`, or `final-review`.
2. Write a concise task statement with the goal, relevant constraints, commands already run, and the specific question for Codex.
3. Do not include secrets, `.env` values, personal data, or raw production data.
4. Run:

```powershell
powershell -File .claude/scripts/codex-consult.ps1 <mode> "<task statement>"
```

5. Read the generated report. Validate findings against repository files and test output.
6. Continue implementation only after integrating or consciously rejecting each material finding.

## Mode selection

- `plan-review`: assess scope, ordering, risks, compatibility, and missing tests before implementation.
- `failure-analysis`: identify likely root causes and minimal diagnostic steps after a focused repair did not resolve a test failure.
- `final-review`: review the current Git diff for correctness, regressions, security concerns, and test gaps.

Codex is an advisor. It must not edit files, run destructive commands, create commits, or decide completion.
