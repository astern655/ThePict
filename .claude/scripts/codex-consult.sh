#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
TASK="${2:-}"

if [[ -z "$MODE" || -z "$TASK" ]]; then
  echo "Usage: $0 {plan-review|failure-analysis|final-review} \"task statement\"" >&2
  exit 64
fi

case "$MODE" in
  plan-review)
    FOCUS="Review the implementation plan. Identify missing requirements, risks, compatibility concerns, implementation order, and essential tests."
    ;;
  failure-analysis)
    FOCUS="Analyze the reported failure. Identify likely root causes, evidence to gather, and the smallest safe next diagnostic or repair step. Do not edit files."
    ;;
  final-review)
    FOCUS="Review the current Git diff against the stated goal. Identify correctness issues, regressions, security concerns, and missing tests, prioritized by severity."
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    exit 64
    ;;
esac

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex CLI is not available in this WSL environment. Install it and run 'codex login'." >&2
  exit 69
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
REPORT_DIR="$ROOT/.claude/docs/codex-reviews"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="$REPORT_DIR/${STAMP}-${MODE}.md"
mkdir -p "$REPORT_DIR"

PROMPT=$(cat <<EOF
You are Codex, acting only as an independent read-only reviewer.

Repository root: $ROOT
Mode: $MODE

$FOCUS

Task statement:
$TASK

Instructions:
- Read CLAUDE.md and AGENTS.md if present.
- Inspect only files relevant to the task and current Git diff when useful.
- Do not modify, create, delete, stage, or commit files.
- Do not request or reveal secrets, personal data, .env values, or production data.
- Return concise Markdown with: Summary, Findings (priority ordered), Evidence, Recommended next steps, and Tests to run.
EOF
)

codex exec --cd "$ROOT" --sandbox read-only --output-last-message "$REPORT" "$PROMPT"
echo "Codex report saved to: $REPORT"
