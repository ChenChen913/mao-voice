# -*- coding: utf-8 -*-
"""自学习纠错引擎（learn.py）单元测试：提取/频次/落盘/提示词拼装。"""
import json

import learn


def test_extract_pairs_basic():
    pairs = learn.extract_pairs("这个配森脚本跑一下", "这个Python脚本跑一下")
    assert ("配森脚本" in "".join(p[0] for p in pairs)) or ("配森" in "".join(p[0] for p in pairs))


def test_extract_pairs_ignores_insert_delete():
    # 插入（语气词删除产生 delete 块）：不应产出规则对
    assert learn.extract_pairs("", "你好") == []
    assert learn.extract_pairs("你好", "") == []
    # 纯删除（嗯 → 空）不进 replace
    raw = "嗯这个"
    final = "这个"
    for tag, *_ in __import__("difflib").SequenceMatcher(None, raw, final).get_opcodes():
        assert tag != "replace"


def test_extract_pairs_ignores_punctuation_only_and_long_blocks():
    # 仅标点差异：无学习价值
    assert learn.extract_pairs("你好。", "你好，") == []
    # 超长改写块（polish 档整句重排）：不沉淀
    long_a = "今天天汽很好我们出去玩吧哈哈哈"
    long_b = "我们出去玩吧今天天气很好哈哈哈哈哈"
    for a, b in learn.extract_pairs(long_a, long_b):
        assert len(a) <= learn.MAX_PAIR_CHARS and len(b) <= learn.MAX_PAIR_CHARS


def test_add_and_min_count_gating(tmp_path):
    store = learn.LearnedRules(path=str(tmp_path / "r.json"), min_count=2)
    store.add("配森脚本", "Python脚本")
    assert store.build_block() == "", "单次出现不应进入生效规则"
    store.add("配森环境", "Python环境")
    block = store.build_block()
    assert "配森 → Python" in block
    assert store.count() == 1


def test_persistence_roundtrip_and_clear(tmp_path):
    p = str(tmp_path / "r.json")
    store = learn.LearnedRules(path=p, min_count=1)
    store.add("配森", "Python")
    # 落盘文件为合法 JSON 且含记录
    data = json.loads(open(p, encoding="utf-8").read())
    assert data and data[0]["wrong"] == "配森"
    # 新实例能读回
    store2 = learn.LearnedRules(path=p, min_count=1)
    assert "配森 → Python" in store2.build_block()
    # 清空后为空
    store2.clear()
    assert learn.LearnedRules(path=p, min_count=1).build_block() == ""


def test_multiple_writings_of_same_wrong_word(tmp_path):
    store = learn.LearnedRules(path=str(tmp_path / "r.json"), min_count=1)
    store.add("配森", "Python")
    store.add("配森", "派森")  # 同一原词两个候选：各自计数
    block = store.build_block()
    # 字符级对齐：配森→Python 整块替换；配森→派森 只替换首字（"森"相同不进 replace）
    assert "Python" in block and "配 → 派" in block


def test_append_learned_block_merge(tmp_path):
    store = learn.LearnedRules(path=str(tmp_path / "r.json"), min_count=1)
    assert learn.append_learned_block("术语：GitHub", None) == "术语：GitHub"
    assert learn.append_learned_block("术语：GitHub", store) == "术语：GitHub"
    store.add("配森", "Python")
    merged = learn.append_learned_block("术语：GitHub", store)
    assert merged.startswith("术语：GitHub") and "配森 → Python" in merged
    # 词库为空（"（无）"）时直接替换为规则块
    only_learn = learn.append_learned_block("（无）", store)
    assert "配森 → Python" in only_learn


def test_prune_keeps_memory_and_disk_bounded(tmp_path):
    """三审 m1：max_rules 截断不仅作用于落盘，内存 _rules 也同步修剪。"""
    store = learn.LearnedRules(path=str(tmp_path / "r.json"), min_count=1, max_rules=3)
    for i in range(5):
        store.add("词{}".format(i), "译{}".format(i))
    assert sum(len(v) for v in store._rules.values()) <= 3
    data = json.loads(open(store.path, encoding="utf-8").read())
    assert len(data) <= 3
