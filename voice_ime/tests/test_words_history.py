# -*- coding: utf-8 -*-
"""词库写入与历史删除的持久化测试。"""
import pytest

from config import load_words, save_words
from history import HistoryStore, clear_entries, read_entries, remove_entry, write_entries


def test_save_words_preserves_comments_and_dedupes(tmp_path):
    path = tmp_path / "词库.txt"
    path.write_text("# 自定义注释\n旧词\n", encoding="utf-8")

    save_words(["新词", "旧词", "新词"], [("配森", "Python"), ("配森", "Python")], str(path))
    terms, mappings = load_words(str(path))
    assert terms == ["新词", "旧词"]
    assert mappings == [("配森", "Python")]

    text = path.read_text(encoding="utf-8")
    assert "# 自定义注释" in text


def test_save_words_rejects_equals_in_term(tmp_path):
    path = tmp_path / "词库.txt"
    with pytest.raises(ValueError):
        save_words(["a=b"], [], str(path))


def test_history_remove_and_clear(tmp_path):
    path = tmp_path / "history.json"
    first = {"ts": "2026-11-01 10:00:00", "raw": "a", "final": "A", "duration_s": 1}
    second = {"ts": "2026-11-01 11:00:00", "raw": "b", "final": "B", "duration_s": 2}
    write_entries([first, second], str(path))

    assert read_entries(str(path)) == [first, second]
    assert remove_entry(first, str(path)) is True
    assert read_entries(str(path)) == [second]

    clear_entries(str(path))
    assert read_entries(str(path)) == []


def test_history_store_remove_stays_in_sync(tmp_path):
    path = tmp_path / "history.json"
    store = HistoryStore(path=str(path))
    store.add("raw", "final-1", duration_s=1)
    store.add("raw", "final-2", duration_s=2)

    entry = store.items()[0]
    assert store.remove(entry) is True
    assert [x["final"] for x in store.items()] == ["final-2"]
    assert [x["final"] for x in read_entries(str(path))] == ["final-2"]
