# -*- coding: utf-8 -*-
"""草稿平滑过渡帧单元测试。"""
import draft_smoother


def _assert_valid(frames, old, new):
    assert 1 <= len(frames) <= 3
    assert frames[-1][0] == new
    assert sum(d for _, d in frames) == 0.3


def test_basic_cases():
    cases = [
        ("", "", "都为空"),
        ("", "新文本", "old 为空"),
        ("旧文本", "", "new 为空"),
        ("不变", "不变", "完全相同"),
        ("我买了杯咖啡", "我买了一杯咖啡，然后去公园", "标准新增"),
        ("我正在喝咖啡呢", "我正在喝一杯热咖啡呢", "公共后缀"),
        ("你好世界", "再见宇宙", "完全不同"),
        ("我买", "我买了一杯咖啡", "前缀关系"),
        ("我买了一杯咖啡然后去公园", "咖啡", "缩减场景"),
    ]
    for old, new, desc in cases:
        frames = draft_smoother.plan_transition(old, new)
        _assert_valid(frames, old, new)
        print(f"  OK {desc}")


def test_duration_guard():
    frames = draft_smoother.plan_transition("a", "b", duration=0)
    assert all(d > 0 for _, d in frames)


def test_long_repeated_text_with_autojunk_disabled():
    # autojunk=False 下，长重复文本仍能找到公共前后缀
    old = "嗯" * 300 + "结尾"
    new = "嗯" * 300 + "结尾二"
    frames = draft_smoother.plan_transition(old, new)
    _assert_valid(frames, old, new)
