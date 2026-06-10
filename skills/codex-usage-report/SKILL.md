---
name: codex-usage-report
description: Use when local Codex session logs need token usage reports by range, timezone, or day/week/month grouping.
---

# Codex Usage Report

Generate token usage reports from local Codex session JSONL logs.

## Command

Prefer `python3`. If the environment only provides `python`, use that as a fallback.

```bash
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --format markdown
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --days 7 --group-by day --timezone Asia/Shanghai
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --month 2026-06 --format json
```

## Output Rules

- Default to `--format markdown` when replying directly to a user.
- Use `--format json` when the result will be parsed, stored, or post-processed.
- Use `--language en` or `--language zh` for the final audience.

## Options

```text
--codex-home
--timezone
--days
--start
--end
--month
--group-by none|day|week|month
--format markdown|json
--language en|zh
```

## Range Rules

- `--month` cannot be combined with `--days`, `--start`, or `--end`.
- `--start/--end` are inclusive dates.
- `--days` means rolling natural days ending on `--end` or the local current day.
- Current-month reports are truncated to the local current day.

## Notes

- The script only aggregates `info.last_token_usage`.
- It ignores invalid JSON, unrelated events, and `token_count` records with `info: null`.
- It scans `~/.codex/sessions` and `~/.codex/archived_sessions` by default.

