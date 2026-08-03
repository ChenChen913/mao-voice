# -*- coding: utf-8 -*-
"""历史记录模块单元测试。"""
import json
from pathlib import Path

from history import HistoryStore


def test_add_and_persist(tmp_path):
    p = str(tmp_path / "history.json")
    h = HistoryStore(p, max_entries=10)
    h.add("原始草稿", "最终文本", duration_s=3.2)
    assert len(h.items()) == 1
    assert h.items()[0]["final"] == "最终文本"

    h2 = HistoryStore(p, max_entries=10)
    assert h2.items()[0]["final"] == "最终文本"  # 重新加载仍存在


def test_max_entries(tmp_path):
    p = str(tmp_path / "history.json")
    h = HistoryStore(p, max_entries=3)
    for i in range(5):
        h.add(f"raw{i}", f"final{i}")
    finals = [x["final"] for x in h.items()]
    assert finals == ["final2", "final3", "final4"]


def test_corrupt_file_tolerant(tmp_path):
    p = tmp_path / "history.json"
    p.write_text("{broken", encoding="utf-8")
    h = HistoryStore(str(p))
    h.add("a", "b")
    assert len(h.items()) == 1


def test_clear(tmp_path):
    p = tmp_path / "history.json"
    h = HistoryStore(str(p))
    h.add("a", "b")
    h.clear()
    assert h.items() == []
    assert json.loads(Path(p).read_text(encoding="utf-8")) == []


def test_zero_duration_recorded(tmp_path):
    p = str(tmp_path / "history.json")
    h = HistoryStore(p)
    h.add("a", "b", duration_s=0)
    assert h.items()[0]["duration_s"] == 0.0
