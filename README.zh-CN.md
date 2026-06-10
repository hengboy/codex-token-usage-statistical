# Codex Usage Report

`codex-usage-report` 是一个公开 skill，用于把本地 Codex session JSONL 日志整理成 token 用量报表。

它默认扫描 `~/.codex/sessions` 与 `~/.codex/archived_sessions`，对重复 `token_count` 事件去重，按目标时区换算时间，并输出 Markdown 或 JSON。你可以统计全部可用数据，也可以按滚动天数、显式日期区间或自然月生成报表。

## 安装

```bash
npx skills add https://github.com/hengboy/codex-token-usage-statistical.git
```

## Skill 结构

```text
skills/codex-usage-report/
  SKILL.md
  agents/openai.yaml
  scripts/codex_usage_report.py
  scripts/test_codex_usage_report.py
```

## 命令行

```bash
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --format markdown
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --days 7 --group-by day
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --month 2026-06 --timezone Asia/Shanghai
python3 -B skills/codex-usage-report/scripts/codex_usage_report.py --start 2026-06-01 --end 2026-06-10 --format json
```

## 输出

- Markdown：适合直接回复给用户
- JSON：适合自动化和二次处理

JSON 输出固定包含：

- `meta`
- `summary`
- `highlights`
- `breakdown`

## 验证

```bash
python3 -B skills/codex-usage-report/scripts/test_codex_usage_report.py
```

