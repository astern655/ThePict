<#
.SYNOPSIS
    PowerShell port of codex-consult.sh — read-only Codex CLI review helper.

.DESCRIPTION
    Runs `codex.cmd exec --sandbox read-only` non-interactively for one of
    three review modes and saves the report under .claude/docs/codex-reviews.

.PARAMETER Mode
    One of: plan-review, failure-analysis, final-review

.PARAMETER Task
    Free-text task statement passed to Codex.

.EXAMPLE
    powershell -File .claude/scripts/codex-consult.ps1 plan-review "Add auth middleware across 4 files"
#>

param(
    [Parameter(Position = 0)]
    [string]$Mode,

    [Parameter(Position = 1)]
    [string]$Task
)

$ErrorActionPreference = "Stop"

function Show-Usage {
    Write-Error "Usage: codex-consult.ps1 {plan-review|failure-analysis|final-review} `"task statement`""
}

if ([string]::IsNullOrWhiteSpace($Mode) -or [string]::IsNullOrWhiteSpace($Task)) {
    Show-Usage
    exit 64
}

switch ($Mode) {
    "plan-review" {
        $Focus = "Review the implementation plan. Identify missing requirements, risks, compatibility concerns, implementation order, and essential tests."
    }
    "failure-analysis" {
        $Focus = "Analyze the reported failure. Identify likely root causes, evidence to gather, and the smallest safe next diagnostic or repair step. Do not edit files."
    }
    "final-review" {
        $Focus = "Review the current Git diff against the stated goal. Identify correctness issues, regressions, security concerns, and missing tests, prioritized by severity."
    }
    default {
        Write-Error "Unknown mode: $Mode"
        exit 64
    }
}

# Explicitly resolve codex.cmd — never codex.ps1 — so the read-only exec
# contract below is guaranteed regardless of PATHEXT resolution order.
$codexCmd = Get-Command "codex.cmd" -ErrorAction SilentlyContinue
if (-not $codexCmd) {
    Write-Error "Codex CLI (codex.cmd) is not available on PATH. Install it and run 'codex login'."
    exit 69
}

$RepoRoot = $null
try {
    $gitTop = git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitTop) {
        $RepoRoot = $gitTop.Trim()
    }
} catch {
    $RepoRoot = $null
}
if (-not $RepoRoot) {
    $RepoRoot = (Get-Location).Path
}

$ReportDir = Join-Path $RepoRoot ".claude/docs/codex-reviews"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

$Stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$Report = Join-Path $ReportDir "$Stamp-$Mode.md"

$Prompt = @"
You are Codex, acting only as an independent read-only reviewer.

Repository root: $RepoRoot
Mode: $Mode

$Focus

Task statement:
$Task

Instructions:
- Read CLAUDE.md and AGENTS.md if present.
- Inspect only files relevant to the task and current Git diff when useful.
- Do not modify, create, delete, stage, or commit files.
- Do not request or reveal secrets, personal data, .env values, or production data.
- Return concise Markdown with: Summary, Findings (priority ordered), Evidence, Recommended next steps, and Tests to run.
"@

# Codex exec appends piped stdin as an extra <stdin> block even when a
# prompt argument is given, and blocks waiting for EOF if stdin is left
# open (as it is under this harness). Piping a single empty string closes
# stdin immediately so exec proceeds non-interactively.
"" | & $codexCmd.Source exec `
    --cd $RepoRoot `
    --sandbox read-only `
    --skip-git-repo-check `
    --output-last-message $Report `
    $Prompt

if ($LASTEXITCODE -ne 0) {
    Write-Error "codex exec failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

if (-not (Test-Path $Report)) {
    Write-Error "codex exec reported success but no report was written to: $Report"
    exit 70
}

Write-Output "Codex report saved to: $Report"
