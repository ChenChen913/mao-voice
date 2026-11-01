# -*- coding: utf-8 -*-
"""使用统计汇总测试。"""
from datetime import datetime

from stats import summarize


def test_summarize_totals_daily_and_apps():
    now = datetime(2026, 11, 1, 12, 0, 0)
    entries = [
        {"ts": "2026-10-31 09:00:00", "final": "abc", "duration_s": 2, "app": "VS Code"},
        {"ts": "2026-11-01 10:00:00", "final": "defgh", "duration_s": 4, "app": "VS Code"},
        {"ts": "2026-11-01 11:00:00", "final": "ij", "duration_s": "bad", "app": "终端"},
        {"ts": "bad", "final": "klm", "duration_s": 1},
        {"ts": "2026-11-01 12:00:00", "final": ""},
    ]
    summary = summarize(entries, now=now, days=7)

    assert summary["total_entries"] == 4
    assert summary["total_chars"] == 13
    assert summary["total_seconds"] == 7
    assert summary["saved_minutes"] == 0
    assert summary["daily"][-2] == ("10-31", 3)
    assert summary["daily"][-1] == ("11-01", 7)
    assert summary["apps"][0] == ("VS Code", 8)


def test_summarize_empty():
    summary = summarize([])
    assert summary["total_entries"] == 0
    assert len(summary["daily"]) == 7
    assert summary["apps"] == []
