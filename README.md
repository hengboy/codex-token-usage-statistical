# Codex Usage Report

`codex-usage-report` is a public skill for turning local Codex session JSONL logs into token usage reports.

It scans `~/.codex/sessions` and `~/.codex/archived_sessions`, deduplicates repeated `token_count` events, converts timestamps into your target timezone, and renders either Markdown or JSON output. Reports can summarize all available data or focus on rolling days, explicit date ranges, or a calendar month.

## Install

```bash
git clone git@github.com:hengboy/codex-token-usage-statistical.git /tmp/codex-token-usage-statistical
mkdir -p ~/.codex/skills
cp -R /tmp/codex-token-usage-statistical/skills/codex-usage-report ~/.codex/skills/
```

Codex loads local skills from `~/.codex/skills`.

## Skill Layout

```text
skills/codex-usage-report/
  SKILL.md
  agents/openai.yaml
  scripts/codex_usage_report.py
  scripts/test_codex_usage_report.py
```

## CLI

```bash
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --format markdown
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --days 7 --group-by day
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --month 2026-06 --timezone Asia/Shanghai
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --start 2026-06-01 --end 2026-06-10 --format json
```

## Output

- Markdown: optimized for direct replies to users
- JSON: optimized for automation and downstream processing

JSON output always contains:

- `meta`
- `summary`
- `highlights`
- `breakdown`

## Verify

```bash
python3 -B skills/codex-usage-report/scripts/test_codex_usage_report.py
```
