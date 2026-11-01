# -*- coding: utf-8 -*-
"""使用统计：从历史条目汇总字数、时长与按天/按应用分布（纯函数便于测试）。"""
from datetime import datetime, timedelta


def _parse(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def summarize(entries, now=None, days=7):
    """返回总览与近 N 天/按应用分布。

    结构：
    total_entries / total_chars / total_seconds / saved_minutes
    daily: [(月-日, 字数), ...] 长度固定为 days
    apps: [(应用名, 字数), ...] 按字数降序
    """
    now = now or datetime.now()
    entries = [x for x in (entries or []) if isinstance(x, dict) and x.get("final")]
    total_chars = sum(len(x.get("final", "")) for x in entries)
    total_seconds = 0.0
    for item in entries:
        try:
            total_seconds += float(item.get("duration_s") or 0)
        except (TypeError, ValueError):
            pass

    today = now.date()
    buckets = {}
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        buckets[day] = 0
    for item in entries:
        dt = _parse(item.get("ts", ""))
        if dt is None:
            continue
        day = dt.date()
        if day in buckets:
            buckets[day] += len(item.get("final", ""))

    app_totals = {}
    for item in entries:
        name = str(item.get("app") or "未记录")
        app_totals[name] = app_totals.get(name, 0) + len(item.get("final", ""))
    apps = sorted(app_totals.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "total_entries": len(entries),
        "total_chars": total_chars,
        "total_seconds": total_seconds,
        "saved_minutes": max(0, total_chars // 40),
        "daily": [(day.strftime("%m-%d"), chars) for day, chars in buckets.items()],
        "apps": apps,
    }
