#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


GROUP_CHOICES = ("none", "day", "week", "month")
FORMAT_CHOICES = ("markdown", "json")
LANGUAGE_CHOICES = ("en", "zh")


TRANSLATIONS = {
    "en": {
        "range": "Range",
        "timezone": "Timezone",
        "calls": "Calls",
        "sessions": "Sessions",
        "active_days": "Active Days",
        "summary": "Summary",
        "highlights": "Highlights",
        "breakdown": "Breakdown",
        "metric": "Metric",
        "value": "Value",
        "total": "Total Tokens",
        "input": "Input Tokens",
        "cached_input": "Cached Input Tokens",
        "non_cached_input": "Non-Cached Input Tokens",
        "output": "Output Tokens",
        "reasoning_output": "Reasoning Output Tokens",
        "net_usage": "Net Usage Tokens",
        "cache_hit_rate": "Cache Hit Rate",
        "daily_average_total": "Daily Average Total",
        "active_day_average_total": "Active-Day Average Total",
        "period": "Period",
        "start": "Start",
        "end": "End",
        "peak_day": "Peak day",
        "peak_week": "Peak week",
        "peak_month": "Peak month",
        "none": "N/A",
        "through": "through",
    },
    "zh": {
        "range": "范围",
        "timezone": "时区",
        "calls": "调用次数",
        "sessions": "会话数",
        "active_days": "活跃天数",
        "summary": "汇总",
        "highlights": "亮点",
        "breakdown": "分组明细",
        "metric": "指标",
        "value": "数值",
        "total": "总 Token",
        "input": "输入 Token",
        "cached_input": "缓存输入 Token",
        "non_cached_input": "非缓存输入 Token",
        "output": "输出 Token",
        "reasoning_output": "推理输出 Token",
        "net_usage": "净用量 Token",
        "cache_hit_rate": "缓存命中率",
        "daily_average_total": "日均总 Token",
        "active_day_average_total": "活跃日均总 Token",
        "period": "周期",
        "start": "开始",
        "end": "结束",
        "peak_day": "最高的一天",
        "peak_week": "最高的一周",
        "peak_month": "最高的一月",
        "none": "无",
        "through": "至",
    },
}


@dataclass(frozen=True)
class UsageEntry:
    session_id: str
    timestamp: datetime
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int

    def local_datetime(self, tz: ZoneInfo) -> datetime:
        return self.timestamp.astimezone(tz)

    def local_date(self, tz: ZoneInfo) -> date:
        return self.local_datetime(tz).date()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Codex token usage reports from local session logs.")
    parser.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    parser.add_argument("--timezone", default=None)
    parser.add_argument("--days", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--month")
    parser.add_argument("--group-by", choices=GROUP_CHOICES, default="none")
    parser.add_argument("--format", choices=FORMAT_CHOICES, default="markdown")
    parser.add_argument("--language", choices=LANGUAGE_CHOICES, default="en")
    return parser.parse_args(argv)


def detect_local_timezone() -> tuple[ZoneInfo, str]:
    tz_name = os.environ.get("TZ")
    if tz_name:
        try:
            return ZoneInfo(tz_name), tz_name
        except Exception:
            pass
    local = datetime.now().astimezone().tzinfo
    if isinstance(local, ZoneInfo):
        return local, getattr(local, "key", str(local))
    return ZoneInfo("UTC"), "UTC"


def resolve_timezone(name: str | None) -> tuple[ZoneInfo, str]:
    if not name:
        return detect_local_timezone()
    try:
        return ZoneInfo(name), name
    except Exception as exc:
        raise SystemExit(f"Invalid timezone: {name}") from exc


def parse_date(value: str, flag: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"Invalid {flag} date: {value}") from exc


def month_bounds(month_value: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(f"{month_value}-01")
    except ValueError as exc:
        raise SystemExit(f"Invalid --month value: {month_value}") from exc
    if start.month == 12:
        next_month = date(start.year + 1, 1, 1)
    else:
        next_month = date(start.year, start.month + 1, 1)
    return start, next_month - timedelta(days=1)


def resolve_range(
    args: argparse.Namespace,
    tz: ZoneInfo,
    now: datetime | None = None,
) -> tuple[date | None, date | None]:
    if args.month and any(value is not None for value in (args.days, args.start, args.end)):
        raise SystemExit("--month cannot be combined with --days, --start, or --end")
    if args.days is not None and args.start is not None:
        raise SystemExit("--days cannot be combined with --start")
    if args.days is not None and args.days <= 0:
        raise SystemExit("--days must be greater than 0")

    today = (now or datetime.now(tz)).astimezone(tz).date()
    if args.month:
        start_date, end_date = month_bounds(args.month)
        if start_date.year == today.year and start_date.month == today.month:
            end_date = min(end_date, today)
        return start_date, end_date

    end_date = parse_date(args.end, "--end") if args.end else None
    start_date = parse_date(args.start, "--start") if args.start else None
    if args.days is not None:
        end_anchor = end_date or today
        start_date = end_anchor - timedelta(days=args.days - 1)
        end_date = end_anchor
    if start_date and end_date and start_date > end_date:
        raise SystemExit("--start cannot be after --end")
    return start_date, end_date


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def iter_session_files(codex_home: Path) -> Iterable[Path]:
    for name in ("sessions", "archived_sessions"):
        root = codex_home / name
        if not root.exists():
            continue
        yield from sorted(path for path in root.rglob("*.jsonl") if path.is_file())


def load_entries(codex_home: Path) -> list[UsageEntry]:
    entries: list[UsageEntry] = []
    seen: set[tuple[str, str, int, int, int, int, int]] = set()

    for path in iter_session_files(codex_home):
        session_id = path.stem
        try:
            with path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    try:
                        obj = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    if obj.get("type") == "session_meta":
                        payload = obj.get("payload")
                        if isinstance(payload, dict) and payload.get("id"):
                            session_id = str(payload["id"])
                        continue

                    if obj.get("type") != "event_msg":
                        continue
                    payload = obj.get("payload")
                    if not isinstance(payload, dict) or payload.get("type") != "token_count":
                        continue
                    info = payload.get("info")
                    if not isinstance(info, dict):
                        continue
                    last_usage = info.get("last_token_usage")
                    if not isinstance(last_usage, dict):
                        continue

                    timestamp_text = obj.get("timestamp")
                    if not isinstance(timestamp_text, str):
                        continue
                    timestamp = parse_timestamp(timestamp_text)
                    if timestamp is None:
                        continue

                    input_tokens = int(last_usage.get("input_tokens") or 0)
                    cached_input_tokens = int(last_usage.get("cached_input_tokens") or 0)
                    output_tokens = int(last_usage.get("output_tokens") or 0)
                    reasoning_output_tokens = int(last_usage.get("reasoning_output_tokens") or 0)
                    total_tokens = int(last_usage.get("total_tokens") or 0)

                    dedupe_key = (
                        session_id,
                        timestamp_text,
                        input_tokens,
                        cached_input_tokens,
                        output_tokens,
                        reasoning_output_tokens,
                        total_tokens,
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    entries.append(
                        UsageEntry(
                            session_id=session_id,
                            timestamp=timestamp,
                            input_tokens=input_tokens,
                            cached_input_tokens=cached_input_tokens,
                            output_tokens=output_tokens,
                            reasoning_output_tokens=reasoning_output_tokens,
                            total_tokens=total_tokens,
                        )
                    )
        except OSError:
            continue
    return entries


def filter_entries(entries: Iterable[UsageEntry], tz: ZoneInfo, start_date: date | None, end_date: date | None) -> list[UsageEntry]:
    filtered: list[UsageEntry] = []
    for entry in entries:
        local_day = entry.local_date(tz)
        if start_date and local_day < start_date:
            continue
        if end_date and local_day > end_date:
            continue
        filtered.append(entry)
    return filtered


def bucket_for_date(local_day: date, group_by: str) -> tuple[str, date, date]:
    if group_by == "day":
        return local_day.isoformat(), local_day, local_day
    if group_by == "week":
        start = local_day - timedelta(days=local_day.weekday())
        end = start + timedelta(days=6)
        iso_year, iso_week, _ = local_day.isocalendar()
        return f"{iso_year}-W{iso_week:02d}", start, end
    if group_by == "month":
        start = local_day.replace(day=1)
        _, end = month_bounds(start.strftime("%Y-%m"))
        return start.strftime("%Y-%m"), start, end
    raise ValueError(f"Unsupported group_by: {group_by}")


def safe_div(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def round_rate(value: float) -> float:
    return round(value * 100, 2)


def build_metrics(entries: list[UsageEntry], tz: ZoneInfo, start_date: date | None, end_date: date | None) -> dict[str, object]:
    dates = sorted({entry.local_date(tz) for entry in entries})
    resolved_start = start_date or (dates[0] if dates else None)
    resolved_end = end_date or (dates[-1] if dates else None)
    range_days = ((resolved_end - resolved_start).days + 1) if resolved_start and resolved_end else 0

    total = sum(entry.total_tokens for entry in entries)
    input_tokens = sum(entry.input_tokens for entry in entries)
    cached_input_tokens = sum(entry.cached_input_tokens for entry in entries)
    output_tokens = sum(entry.output_tokens for entry in entries)
    reasoning_output_tokens = sum(entry.reasoning_output_tokens for entry in entries)
    non_cached_input_tokens = input_tokens - cached_input_tokens
    net_usage = total - cached_input_tokens
    active_days = len(dates)

    return {
        "calls": len(entries),
        "sessions": len({entry.session_id for entry in entries}),
        "active_days": active_days,
        "total": total,
        "input": input_tokens,
        "cached_input": cached_input_tokens,
        "output": output_tokens,
        "reasoning_output": reasoning_output_tokens,
        "non_cached_input": non_cached_input_tokens,
        "net_usage": net_usage,
        "cache_hit_rate": round_rate(safe_div(cached_input_tokens, input_tokens)),
        "daily_average_total": round(safe_div(total, range_days), 2) if range_days else 0.0,
        "active_day_average_total": round(safe_div(total, active_days), 2) if active_days else 0.0,
    }


def build_row(label: str, period_start: date, period_end: date, entries: list[UsageEntry], tz: ZoneInfo) -> dict[str, object]:
    row = {
        "label": label,
        "start": period_start.isoformat(),
        "end": period_end.isoformat(),
    }
    row.update(build_metrics(entries, tz, period_start, period_end))
    return row


def build_breakdown(entries: list[UsageEntry], tz: ZoneInfo, group_by: str) -> list[dict[str, object]]:
    buckets: dict[tuple[date, str], list[UsageEntry]] = defaultdict(list)
    boundaries: dict[tuple[date, str], tuple[date, date]] = {}
    for entry in entries:
        label, period_start, period_end = bucket_for_date(entry.local_date(tz), group_by)
        key = (period_start, label)
        buckets[key].append(entry)
        boundaries[key] = (period_start, period_end)

    rows: list[dict[str, object]] = []
    for key in sorted(buckets):
        period_start, label = key
        bucket_entries = buckets[key]
        _, period_end = boundaries[key]
        rows.append(build_row(label, period_start, period_end, bucket_entries, tz))
    return rows


def pick_peak(entries: list[UsageEntry], tz: ZoneInfo, group_by: str) -> dict[str, object] | None:
    rows = build_breakdown(entries, tz, group_by)
    if not rows:
        return None
    return max(rows, key=lambda row: (int(row["total"]), -date.fromisoformat(str(row["start"])).toordinal()))


def build_report(
    entries: list[UsageEntry],
    tz: ZoneInfo,
    timezone_name: str,
    start_date: date | None,
    end_date: date | None,
    group_by: str,
) -> dict[str, object]:
    summary = build_metrics(entries, tz, start_date, end_date)
    filtered_dates = sorted({entry.local_date(tz) for entry in entries})
    meta_start = start_date or (filtered_dates[0] if filtered_dates else None)
    meta_end = end_date or (filtered_dates[-1] if filtered_dates else None)
    days = ((meta_end - meta_start).days + 1) if meta_start and meta_end else 0

    breakdown = None
    if group_by != "none":
        breakdown = {
            "group_by": group_by,
            "rows": build_breakdown(entries, tz, group_by),
        }

    return {
        "meta": {
            "start": meta_start.isoformat() if meta_start else None,
            "end": meta_end.isoformat() if meta_end else None,
            "timezone": timezone_name,
            "days": days,
            "group_by": group_by,
        },
        "summary": summary,
        "highlights": {
            "peak_day": pick_peak(entries, tz, "day"),
            "peak_week": pick_peak(entries, tz, "week"),
            "peak_month": pick_peak(entries, tz, "month"),
        },
        "breakdown": breakdown,
    }


def format_number(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def format_percent(value: object) -> str:
    if isinstance(value, (float, int)):
        return f"{float(value):.2f}%"
    return str(value)


def format_range(meta: dict[str, object], strings: dict[str, str]) -> str:
    start = meta.get("start")
    end = meta.get("end")
    if not start or not end:
        return strings["none"]
    return f"{start} {strings['through']} {end}"


def render_markdown(report: dict[str, object], language: str) -> str:
    strings = TRANSLATIONS[language]
    meta = report["meta"]
    summary = report["summary"]
    highlights = report["highlights"]
    lines = [
        f"- {strings['range']}: {format_range(meta, strings)}",
        f"- {strings['timezone']}: {meta['timezone']}",
        f"- {strings['calls']}: {summary['calls']}",
        f"- {strings['sessions']}: {summary['sessions']}",
        f"- {strings['active_days']}: {summary['active_days']}",
        "",
        f"## {strings['summary']}",
        "",
        f"| {strings['metric']} | {strings['value']} |",
        "| --- | ---: |",
        f"| {strings['total']} | {format_number(summary['total'])} |",
        f"| {strings['input']} | {format_number(summary['input'])} |",
        f"| {strings['cached_input']} | {format_number(summary['cached_input'])} |",
        f"| {strings['non_cached_input']} | {format_number(summary['non_cached_input'])} |",
        f"| {strings['output']} | {format_number(summary['output'])} |",
        f"| {strings['reasoning_output']} | {format_number(summary['reasoning_output'])} |",
        f"| {strings['net_usage']} | {format_number(summary['net_usage'])} |",
        f"| {strings['cache_hit_rate']} | {format_percent(summary['cache_hit_rate'])} |",
        f"| {strings['daily_average_total']} | {format_number(summary['daily_average_total'])} |",
        f"| {strings['active_day_average_total']} | {format_number(summary['active_day_average_total'])} |",
        "",
        f"## {strings['highlights']}",
        "",
        f"- {strings['peak_day']}: {render_highlight(highlights['peak_day'], strings)}",
        f"- {strings['peak_week']}: {render_highlight(highlights['peak_week'], strings)}",
        f"- {strings['peak_month']}: {render_highlight(highlights['peak_month'], strings)}",
    ]

    breakdown = report["breakdown"]
    if breakdown:
        lines.extend(
            [
                "",
                f"## {strings['breakdown']}",
                "",
                f"| {strings['period']} | {strings['start']} | {strings['end']} | {strings['calls']} | {strings['sessions']} | {strings['total']} | {strings['input']} | {strings['cached_input']} | {strings['output']} | {strings['net_usage']} |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in breakdown["rows"]:
            lines.append(
                f"| {row['label']} | {row['start']} | {row['end']} | {row['calls']} | {row['sessions']} | {row['total']} | {row['input']} | {row['cached_input']} | {row['output']} | {row['net_usage']} |"
            )
    return "\n".join(lines)


def render_highlight(row: dict[str, object] | None, strings: dict[str, str]) -> str:
    if not row:
        return strings["none"]
    return f"{row['label']} ({strings['total']}: {row['total']}, {strings['calls']}: {row['calls']})"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tz, timezone_name = resolve_timezone(args.timezone)
    start_date, end_date = resolve_range(args, tz)
    report = build_report(
        filter_entries(load_entries(Path(args.codex_home).expanduser()), tz, start_date, end_date),
        tz,
        timezone_name,
        start_date,
        end_date,
        args.group_by,
    )

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report, args.language))
    return 0


if __name__ == "__main__":
    sys.exit(main())
