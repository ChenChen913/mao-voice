"""
草稿一致性平滑模块（draft_smoother）。

核心职责：给定旧草稿文本和新文本，生成一组「过渡帧」序列，
让悬浮窗在两个版本之间平滑渐变，避免文本瞬间突变带来的视觉不适。

纯标准库实现，依赖 difflib.SequenceMatcher 做字符级对齐分析。
"""

import difflib


def plan_transition(old: str, new: str, duration: float = 0.3) -> list[tuple[str, float]]:
    """生成从 old 到 new 的过渡帧序列。

    每帧为 (显示文本, 停留秒数)。首帧保留旧文本特征，
    末帧必定等于 new；帧数控制在 1~3 帧。

    参数：
        old:      当前悬浮窗显示的文本（可能为空）。
        new:      目标文本（可能为空）。
        duration: 过渡总时长（秒），默认 0.3 秒。

    返回：
        [(文本, 秒数), ...]  按播放顺序排列的帧序列。
    """
    # ── 边界情况：任一为空或二者完全相同 ──
    # 这类情况下不需要做过渡动画，直接显示目标文本即可。
    if not old and not new:
        return [("", duration)]
    if not old:
        return [(new, duration)]
    if not new:
        return [("", duration)]
    if old == new:
        return [(new, duration)]

    # ── 核心算法：用 SequenceMatcher 找公共前缀/后缀 ──
    # SequenceMatcher.get_matching_blocks() 返回所有匹配子序列，
    # 第一个块若起点为 (0,0) 即公共前缀，最后一个块若延伸到末尾即公共后缀。
    sm = difflib.SequenceMatcher(None, old, new)
    blocks = sm.get_matching_blocks()  # 最后一个块是哨兵 (len(a), len(b), 0)

    # 公共前缀：从位置 0 开始的最长连续匹配
    prefix_len = 0
    for b in blocks:
        if b.a == 0 and b.b == 0:
            prefix_len = b.size
            break

    # 公共后缀：延伸到两字符串末尾的最长连续匹配
    suffix_len = 0
    for b in reversed(blocks):
        if b.size == 0:
            continue  # 跳过哨兵块
        if b.a + b.size == len(old) and b.b + b.size == len(new):
            suffix_len = b.size
            break

    # SequenceMatcher.get_matching_blocks() 返回非重叠、不递减的匹配块，
    # 因此前缀和后缀不可能重叠，无需做 overlap 修正。

    # ── 判断差异程度，决定帧策略 ──
    # 如果 old 所有字符都被公共前缀+后缀覆盖，说明 old 是 new 的子序列
    # （或 new 是 old 的子序列），新旧之间没有"需要隐藏"的突变区域，
    # 直接两帧过渡即可，不需要 "…" 占位帧。
    covered = prefix_len + suffix_len
    if covered >= min(len(old), len(new)):
        # 完全包含关系：old → new 两帧渐变
        dwell1 = duration * 0.30
        return [
            (old, dwell1),
            (new, duration - dwell1),
        ]

    # ── 构造中间帧：公共部分保留，差异部分用 "…" 占位 ──
    # 使用 new 的公共部分构建中间帧，视觉上暗示"文本正向目标靠拢"。
    # 例如 old="我买了杯咖啡", new="我买了一杯咖啡，然后去公园"
    #     → prefix="我买了", suffix="" → 中间帧="我买了…"
    # 又如 old="正在喝咖啡呢", new="正在喝一杯热咖啡呢"
    #     → prefix="正在喝", suffix="咖啡呢" → 中间帧="正在喝…咖啡呢"
    if suffix_len > 0:
        intermediate = new[:prefix_len] + "…" + new[-suffix_len:]
    else:
        if prefix_len > 0:
            intermediate = new[:prefix_len] + "…"
        else:
            # 没有任何公共字符：old 和 new 完全不同，用纯 "…" 做过渡
            intermediate = "…"

    # ── 三帧过渡：old 短暂停留 → "…" 过渡提示 → new 最终展示 ──
    # 时长分配：15% 留在旧文本，25% 显示过渡提示，60% 展示最终结果。
    # 关键：尾帧用 duration - sum(前两帧) 代替乘法，避免 IEEE-754 浮点累积误差。
    dwell1 = duration * 0.15
    dwell2 = duration * 0.25
    return [
        (old, dwell1),
        (intermediate, dwell2),
        (new, duration - dwell1 - dwell2),
    ]


# ── 冒烟测试 ──
if __name__ == "__main__":
    def _test(old, new, desc=""):
        frames = plan_transition(old, new, duration=0.3)
        total = sum(f[1] for f in frames)
        print(f"[{desc}]")
        print(f"  old={old!r} → new={new!r}")
        for i, (txt, dur) in enumerate(frames):
            bar = "█" * int(dur * 100)
            print(f"  帧{i}: {txt!r}  ({dur:.2f}s) {bar}")
        assert frames[-1][0] == new, f"末帧应为 new 而实际为 {frames[-1][0]!r}"
        assert 1 <= len(frames) <= 4, f"帧数应为 1~4 而实际为 {len(frames)}"
        assert abs(total - 0.3) < 1e-9, f"总时长应为 0.3 而实际为 {total}"
        print("  ✓ 通过\n")

    # 标准场景：新增内容 + 措辞微调
    _test("我买了杯咖啡", "我买了一杯咖啡，然后去公园", "标准场景-新增词汇")

    # 有公共后缀的场景
    _test("我正在喝咖啡呢", "我正在喝一杯热咖啡呢", "有公共后缀")

    # 完全不同的文本
    _test("你好世界", "再见宇宙", "完全不同")

    # old 是 new 的前缀（包含关系）
    _test("我买", "我买了一杯咖啡", "old是new前缀")

    # old 为空
    _test("", "新文本", "old为空")

    # new 为空
    _test("旧文本", "", "new为空")

    # 完全相同
    _test("不变", "不变", "完全相同")

    # 二者都为空
    _test("", "", "都为空")

    # new 比 old 短（缩减场景）
    _test("我买了一杯咖啡然后去公园", "咖啡", "缩减场景")

    # 中文单字差异
    _test("红的", "蓝色", "单字差异-无公共")

    print("全部冒烟测试通过 ✓")
