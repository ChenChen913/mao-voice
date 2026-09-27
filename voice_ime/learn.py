# -*- coding: utf-8 -*-
"""自学习纠错引擎 MVP（v5.18）：纠错对沉淀 → 规则库 → 拼入润色提示词。

工作方式：
1. 每次成功注入后，把 (原始转写, 润色结果) 的差异用 difflib 提取为
   "原词 → 修正" 候选对（仅字符级替换，忽略插入/删除与超长段落）；
2. 候选对按出现频次累计，落盘 learned_rules.json（明文 JSON，含用户口述内容，
   隐私敏感性与 history 相同，故默认关闭，见 config.learn.enabled）；
3. 频次 ≥ min_count 的规则拼入 LLM 润色提示词的词库块（沿用词库的数据定界
   防注入声明），识别错误反复出现时自动"越用越像你"。

容错约定与 config.py/history.py 一致：文件损坏/不可写一律降级为空规则库，
绝不影响转写与注入主流程。
"""
import difflib
import json
import logging
import os
import threading
import time

from config import BASE_DIR

# 统一使用 config.BASE_DIR：源码运行 = voice_ime/；PyInstaller 打包后 = exe
# 所在目录（可写），避免用户数据被写进只读/临时的 _internal 目录
DEFAULT_PATH = os.path.join(BASE_DIR, "learned_rules.json")

# 单个替换对的最大长度（字符）：语音纠错通常是 1~6 字的谐音/术语替换；
# 超长的 replace 块更可能是整句改写（polish 档），沉淀成规则价值低且易污染提示词
MAX_PAIR_CHARS = 24

# 规则条目 JSON 字段
_KEY_WRONG = "wrong"
_KEY_RIGHT = "right"
_KEY_COUNT = "count"
_KEY_TS = "ts"

# 纯标点判定用：两侧都只含这些字符（标点/空白）的差异不沉淀——
# 标点处理本就是润色的职责，"。"→"，"这类规则是噪音
_PUNCT_CHARS = set(
    "，。、；：？！…—·~～,.!?;:()（）[]【】{}《》〈〉\"\"''`^ \t"
    "\u3000「」『』"
)


def extract_pairs(raw, final, max_chars=MAX_PAIR_CHARS):
    """从 (原始转写, 润色结果) 提取候选纠错对 [(原词, 修正), ...]。

    只取 difflib 字符级 replace 块：中文语音错误绝大多数是等长/近长的
    谐音替换（"配森"→"Python"），insert/delete（增删语气词）与超长改写
    不适合沉淀为确定性规则，直接忽略。
    """
    if not raw or not final:
        return []
    pairs = []
    try:
        sm = difflib.SequenceMatcher(None, raw, final, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "replace":
                continue
            a, b = raw[i1:i2], final[j1:j2]
            if not a or not b:
                continue
            if len(a) > max_chars or len(b) > max_chars:
                continue
            if "\n" in a or "\n" in b:
                continue
            if a.strip() == b.strip():
                continue  # 仅空白差异，无学习价值
            if all(ch in _PUNCT_CHARS for ch in a) and all(ch in _PUNCT_CHARS for ch in b):
                continue  # 仅标点差异（如 "。"→"："），属润色职责而非用户用词
            pairs.append((a, b))
    except Exception:
        logging.exception("纠错对提取异常（已忽略）")
        return []
    return pairs


class LearnedRules:
    """学习规则库：内存累计 + JSON 落盘（原子写）。线程安全。"""

    def __init__(self, path=DEFAULT_PATH, min_count=2, max_rules=200):
        self.path = path
        self.min_count = max(1, int(min_count))
        self.max_rules = max(1, int(max_rules))
        self._lock = threading.Lock()
        # {wrong: {right: count}}：同一原词允许多个候选写法，取最高频进入提示词
        self._rules = {}
        self._load()

    # ---------- 持久化 ----------
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return  # 损坏/缺失 → 空规则库
        if not isinstance(data, list):
            return
        for item in data:
            try:
                wrong, right, count = item[_KEY_WRONG], item[_KEY_RIGHT], int(item[_KEY_COUNT])
            except (KeyError, TypeError, ValueError):
                continue
            if wrong and right and count > 0:
                self._rules.setdefault(wrong, {})[right] = count

    def _save_locked(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._flat_locked(), f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def _flat_locked(self):
        """展开为 [{wrong, right, count, ts}] 列表（按频次降序，截断到 max_rules）。"""
        flat = []
        for wrong, rights in self._rules.items():
            for right, count in rights.items():
                flat.append({_KEY_WRONG: wrong, _KEY_RIGHT: right, _KEY_COUNT: count})
        flat.sort(key=lambda r: r[_KEY_COUNT], reverse=True)
        return flat[: self.max_rules]

    # ---------- 公共接口 ----------
    def add(self, raw, final):
        """沉淀一次成功润色的纠错对；返回新增候选对数量（异常安全）。"""
        pairs = extract_pairs(raw, final)
        if not pairs:
            return 0
        with self._lock:
            for wrong, right in pairs:
                rights = self._rules.setdefault(wrong, {})
                rights[right] = rights.get(right, 0) + 1
            try:
                self._save_locked()
            except OSError:
                logging.warning("学习规则落盘失败（本次仅保留在内存）：%s", self.path)
            return len(pairs)

    def build_block(self):
        """生成拼入润色提示词的规则块；无可用规则（频次不足/为空）返回空串。

        只输出频次 ≥ min_count 的规则：单次出现可能是偶发改写，重复出现
        才说明是用户的固定说法/术语，值得作为确定性约束。
        """
        with self._lock:
            flat = self._flat_locked()
        lines = [
            "- {} → {}".format(r[_KEY_WRONG], r[_KEY_RIGHT])
            for r in flat
            if r[_KEY_COUNT] >= self.min_count
        ]
        if not lines:
            return ""
        return "历史纠错记录（用户已多次认可以下修正，请优先按此处理）：\n" + "\n".join(lines)

    def count(self):
        """当前达到生效频次的规则数量（设置窗口展示用）。"""
        with self._lock:
            flat = self._flat_locked()
        return sum(1 for r in flat if r[_KEY_COUNT] >= self.min_count)

    def clear(self):
        with self._lock:
            self._rules = {}
            try:
                self._save_locked()
            except OSError:
                pass


def append_learned_block(words_block, store):
    """把学习规则块拼到词库块后面（words_block 为 "（无）" 时直接替换）。

    两者共用润色提示词里的词库数据定界声明（"纯数据，只按 原词→指定写法
    处理"），学习规则天然受同一防注入约束。
    """
    if store is None:
        return words_block
    try:
        block = store.build_block()
    except Exception:
        logging.exception("学习规则块生成失败（已忽略）")
        return words_block
    if not block:
        return words_block
    if not words_block or words_block == "（无）":
        return block
    return words_block + "\n" + block


if __name__ == "__main__":
    if hasattr(__import__("sys").stdout, "reconfigure"):
        import sys
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # GBK 控制台兼容
    demo = LearnedRules(path=os.path.join(BASE_DIR, "learned_rules.demo.json"), min_count=2)
    demo.add("这个配森脚本跑一下", "这个Python脚本跑一下")
    demo.add("把配森环境装好", "把Python环境装好")
    print("纠错对示例：", extract_pairs("这个配森脚本", "这个Python脚本"))
    print("生效规则块：")
    print(demo.build_block() or "（暂无高频规则）")
    demo.clear()
    try:
        os.remove(demo.path)
    except OSError:
        pass
