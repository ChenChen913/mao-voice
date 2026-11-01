# -*- coding: utf-8 -*-
"""输入历史记录（F12）：内存队列 + 可选 JSON 落盘。

每次成功注入后记录 (时间, 原始转写, 最终文本, 录音时长)；
文件损坏/不可写时静默降级为纯内存，绝不影响输入主流程。
"""
import json
import os
import threading
import time
from collections import deque

from config import BASE_DIR

DEFAULT_PATH = os.path.join(BASE_DIR, "history.json")


def read_entries(path=DEFAULT_PATH):
    """读取历史文件，返回有效条目列表；缺失/损坏时返回空列表。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("final")]


def write_entries(entries, path=DEFAULT_PATH):
    """原子写入历史列表。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(list(entries), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _same_entry(a, b):
    return all(a.get(key) == b.get(key) for key in ("ts", "raw", "final"))


def remove_entry(entry, path=DEFAULT_PATH):
    """按 (时间, 原始, 结果) 删除一条历史；返回是否真的删除了。"""
    items = read_entries(path)
    kept = [x for x in items if not _same_entry(x, entry)]
    if len(kept) == len(items):
        return False
    write_entries(kept, path)
    return True


def clear_entries(path=DEFAULT_PATH):
    """清空历史文件。"""
    write_entries([], path)


class HistoryStore:
    def __init__(self, path=DEFAULT_PATH, max_entries=100):
        self.path = path
        self.max_entries = max(max_entries, 1)
        self._lock = threading.Lock()
        self._items = deque(maxlen=self.max_entries)
        self._load()

    def _load(self):
        for item in read_entries(self.path)[-self.max_entries:]:
            self._items.append(item)

    def add(self, raw, final, duration_s=None):
        with self._lock:
            try:
                duration = round(duration_s, 1) if duration_s is not None else None
            except (TypeError, ValueError):
                duration = None  # v5.14：非法时长降级为 None，不影响记录
            self._items.append({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "raw": raw,
                "final": final,
                "duration_s": duration,
            })
            try:
                self._save_locked()
            except OSError:
                pass  # 落盘失败不影响内存记录

    def _save_locked(self):
        # 与 config.save_config 的原子写入约定一致：rename 前 flush + fsync
        write_entries(self._items, self.path)

    def items(self):
        with self._lock:
            return list(self._items)

    def remove(self, entry):
        """删除一条（按时间+原文+结果匹配），返回是否删除成功。"""
        with self._lock:
            kept = [x for x in self._items if not _same_entry(x, entry)]
            changed = len(kept) != len(self._items)
            self._items = deque(kept, maxlen=self.max_entries)
            if changed:
                try:
                    self._save_locked()
                except OSError:
                    pass
            return changed

    def clear(self):
        with self._lock:
            self._items.clear()
            try:
                self._save_locked()
            except OSError:
                pass
