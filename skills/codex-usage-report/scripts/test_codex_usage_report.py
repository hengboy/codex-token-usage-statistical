#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MODULE_PATH = Path(__file__).with_name("codex_usage_report.py")
SPEC = importlib.util.spec_from_file_location("codex_usage_report", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def token_event(timestamp: str, input_tokens: int, cached_input_tokens: int, output_tokens: int, reasoning_output_tokens: int, total_tokens: int) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens * 10,
                    "cached_input_tokens": cached_input_tokens * 10,
                    "output_tokens": output_tokens * 10,
                    "reasoning_output_tokens": reasoning_output_tokens * 10,
                    "total_tokens": total_tokens * 10,
                },
                "last_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_output_tokens,
                    "total_tokens": total_tokens,
                },
            },
        },
    }


class CodexUsageReportTests(unittest.TestCase):
    maxDiff = None

    def load_report(self, root: Path, *args: str) -> dict[str, object]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = MODULE.main(["--codex-home", str(root), "--format", "json", *args])
        self.assertEqual(exit_code, 0)
        return json.loads(buffer.getvalue())

    def render_markdown(self, root: Path, *args: str) -> str:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = MODULE.main(["--codex-home", str(root), "--format", "markdown", *args])
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def test_summary_metrics_and_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "sessions" / "2026" / "06" / "10" / "rollout-a.jsonl"
            session_path.parent.mkdir(parents=True)
            lines = [
                {"timestamp": "2026-06-10T01:00:00Z", "type": "session_meta", "payload": {"id": "session-a"}},
                token_event("2026-06-10T01:00:00Z", 100, 40, 30, 10, 130),
                token_event("2026-06-10T01:00:00Z", 100, 40, 30, 10, 130),
                token_event("2026-06-10T02:00:00Z", 80, 20, 50, 15, 130),
                {"timestamp": "2026-06-10T03:00:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": None}},
                {"timestamp": "2026-06-10T03:00:00Z", "type": "event_msg", "payload": {"type": "other_event"}},
                "not-json",
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in lines:
                    if isinstance(item, str):
                        handle.write(item + "\n")
                    else:
                        handle.write(json.dumps(item) + "\n")

            report = self.load_report(root)
            summary = report["summary"]
            self.assertEqual(summary["calls"], 2)
            self.assertEqual(summary["sessions"], 1)
            self.assertEqual(summary["active_days"], 1)
            self.assertEqual(summary["total"], 260)
            self.assertEqual(summary["input"], 180)
            self.assertEqual(summary["cached_input"], 60)
            self.assertEqual(summary["output"], 80)
            self.assertEqual(summary["reasoning_output"], 25)
            self.assertEqual(summary["non_cached_input"], 120)
            self.assertEqual(summary["net_usage"], 200)
            self.assertEqual(summary["cache_hit_rate"], 33.33)
            self.assertEqual(summary["daily_average_total"], 260.0)
            self.assertEqual(summary["active_day_average_total"], 260.0)

    def test_timezone_bucketing_and_group_by_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "sessions" / "2026" / "06" / "10" / "rollout-b.jsonl"
            session_path.parent.mkdir(parents=True)
            entries = [
                {"timestamp": "2026-06-10T00:00:00Z", "type": "session_meta", "payload": {"id": "session-b"}},
                token_event("2026-06-10T23:30:00Z", 50, 10, 20, 5, 70),
                token_event("2026-06-11T00:30:00Z", 40, 0, 10, 2, 50),
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in entries:
                    handle.write(json.dumps(item) + "\n")

            report = self.load_report(root, "--timezone", "Asia/Shanghai", "--group-by", "day")
            self.assertEqual(report["meta"]["start"], "2026-06-11")
            self.assertEqual(report["meta"]["end"], "2026-06-11")
            rows = report["breakdown"]["rows"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["label"], "2026-06-11")
            self.assertEqual(rows[0]["total"], 120)

    def test_days_start_end_and_month_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "sessions" / "2026" / "06" / "10" / "rollout-c.jsonl"
            session_path.parent.mkdir(parents=True)
            entries = [
                {"timestamp": "2026-06-01T01:00:00Z", "type": "session_meta", "payload": {"id": "session-c"}},
                token_event("2026-06-01T01:00:00Z", 10, 0, 5, 1, 15),
                token_event("2026-06-05T01:00:00Z", 20, 5, 10, 1, 30),
                token_event("2026-06-10T01:00:00Z", 30, 10, 15, 2, 45),
                token_event("2026-06-25T01:00:00Z", 40, 10, 20, 3, 60),
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in entries:
                    handle.write(json.dumps(item) + "\n")

            tz = ZoneInfo("Asia/Shanghai")
            now = datetime(2026, 6, 18, 12, 0, tzinfo=tz)
            self.assertEqual(MODULE.resolve_range(MODULE.parse_args(["--days", "3", "--end", "2026-06-10"]), tz, now), (MODULE.parse_date("2026-06-08", "--start"), MODULE.parse_date("2026-06-10", "--end")))
            self.assertEqual(MODULE.resolve_range(MODULE.parse_args(["--start", "2026-06-05", "--end", "2026-06-10"]), tz, now), (MODULE.parse_date("2026-06-05", "--start"), MODULE.parse_date("2026-06-10", "--end")))
            self.assertEqual(MODULE.resolve_range(MODULE.parse_args(["--month", "2026-06"]), tz, now), (MODULE.parse_date("2026-06-01", "--month"), MODULE.parse_date("2026-06-18", "--month")))
            self.assertEqual(MODULE.resolve_range(MODULE.parse_args(["--month", "2026-05"]), tz, now), (MODULE.parse_date("2026-05-01", "--month"), MODULE.parse_date("2026-05-31", "--month")))

            report = self.load_report(root, "--start", "2026-06-05", "--end", "2026-06-10")
            self.assertEqual(report["meta"]["start"], "2026-06-05")
            self.assertEqual(report["meta"]["end"], "2026-06-10")
            self.assertEqual(report["summary"]["total"], 75)

            rolling = self.load_report(root, "--days", "3", "--end", "2026-06-10")
            self.assertEqual(rolling["meta"]["start"], "2026-06-08")
            self.assertEqual(rolling["meta"]["end"], "2026-06-10")
            self.assertEqual(rolling["summary"]["total"], 45)

    def test_group_by_week_month_and_peaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "archived_sessions" / "2026" / "06" / "rollout-d.jsonl"
            session_path.parent.mkdir(parents=True)
            entries = [
                {"timestamp": "2026-06-01T01:00:00Z", "type": "session_meta", "payload": {"id": "session-d"}},
                token_event("2026-06-01T01:00:00Z", 10, 0, 5, 1, 15),
                token_event("2026-06-02T01:00:00Z", 20, 0, 10, 1, 30),
                token_event("2026-06-12T01:00:00Z", 30, 5, 15, 2, 45),
                token_event("2026-07-03T01:00:00Z", 40, 10, 20, 3, 60),
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in entries:
                    handle.write(json.dumps(item) + "\n")

            weekly = self.load_report(root, "--group-by", "week")
            self.assertEqual([row["label"] for row in weekly["breakdown"]["rows"]], ["2026-W23", "2026-W24", "2026-W27"])
            self.assertEqual(weekly["highlights"]["peak_week"]["label"], "2026-W27")

            monthly = self.load_report(root, "--group-by", "month")
            self.assertEqual([row["label"] for row in monthly["breakdown"]["rows"]], ["2026-06", "2026-07"])
            self.assertEqual(monthly["highlights"]["peak_month"]["label"], "2026-06")
            self.assertEqual(monthly["highlights"]["peak_day"]["label"], "2026-07-03")

    def test_markdown_language_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "sessions" / "2026" / "06" / "10" / "rollout-e.jsonl"
            session_path.parent.mkdir(parents=True)
            entries = [
                {"timestamp": "2026-06-10T01:00:00Z", "type": "session_meta", "payload": {"id": "session-e"}},
                token_event("2026-06-10T01:00:00Z", 10, 5, 5, 1, 15),
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in entries:
                    handle.write(json.dumps(item) + "\n")

            en_output = self.render_markdown(root, "--language", "en")
            zh_output = self.render_markdown(root, "--language", "zh")
            self.assertIn("- Range:", en_output)
            self.assertIn("## Summary", en_output)
            self.assertIn("- 范围:", zh_output)
            self.assertIn("## 汇总", zh_output)
            self.assertIn("最高的一天", zh_output)

    def test_json_shape_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_path = root / "sessions" / "2026" / "06" / "10" / "rollout-f.jsonl"
            session_path.parent.mkdir(parents=True)
            entries = [
                {"timestamp": "2026-06-10T01:00:00Z", "type": "session_meta", "payload": {"id": "session-f"}},
                token_event("2026-06-10T01:00:00Z", 10, 2, 5, 1, 15),
            ]
            with session_path.open("w", encoding="utf-8") as handle:
                for item in entries:
                    handle.write(json.dumps(item) + "\n")

            report = self.load_report(root, "--group-by", "day")
            self.assertEqual(set(report.keys()), {"meta", "summary", "highlights", "breakdown"})
            self.assertEqual(set(report["meta"].keys()), {"start", "end", "timezone", "days", "group_by"})
            self.assertEqual(
                set(report["summary"].keys()),
                {
                    "calls",
                    "sessions",
                    "active_days",
                    "total",
                    "input",
                    "cached_input",
                    "output",
                    "reasoning_output",
                    "non_cached_input",
                    "net_usage",
                    "cache_hit_rate",
                    "daily_average_total",
                    "active_day_average_total",
                },
            )
            self.assertEqual(set(report["highlights"].keys()), {"peak_day", "peak_week", "peak_month"})
            self.assertEqual(report["breakdown"]["group_by"], "day")
            self.assertEqual(
                set(report["breakdown"]["rows"][0].keys()),
                {
                    "label",
                    "start",
                    "end",
                    "calls",
                    "sessions",
                    "active_days",
                    "total",
                    "input",
                    "cached_input",
                    "output",
                    "reasoning_output",
                    "non_cached_input",
                    "net_usage",
                    "cache_hit_rate",
                    "daily_average_total",
                    "active_day_average_total",
                },
            )


if __name__ == "__main__":
    unittest.main()
