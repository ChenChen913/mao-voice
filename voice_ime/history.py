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

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")


class HistoryStore:
    def __init__(self, path=DEFAULT_PATH, max_entries=100):
        self.path = path
        self.max_entries = max(max_entries, 1)
        self._lock = threading.Lock()
        self._items = deque(maxlen=self.max_entries)
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data[-self.max_entries:]:
                    if isinstance(item, dict) and item.get("final"):
                        self._items.append(item)
        except (OSError, ValueError):
            pass  # 损坏/缺失 → 空历史，不报错

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
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(list(self._items), f, ensure_ascii=False, indent=2)
            # v5.16（m3）：与 config.save_config 的原子写入约定一致——rename 前
            # flush + fsync 落盘，避免断电留下零长/截断文件
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def items(self):
        with self._lock:
            return list(self._items)

    def clear(self):
        with self._lock:
            self._items.clear()
            try:
                self._save_locked()
            except OSError:
                pass
