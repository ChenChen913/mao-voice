"""ASR 引擎：faster-whisper（GPU 优先，CPU 自动回退）。

中文识别准确度调优说明（本次改动，均为可调常量，见下方参数区）：
- beam_size 5→8：解码候选更宽，中文同音词/多音字选词更准；RTX 4060 上 small 模型延迟仍可接受
- condition_on_previous_text=True：整段录音作为连贯上下文解码，长句/多段语义更连贯
- language=None（自动检测）：中英混杂是常见场景，固定 "zh" 会把英文词压成中文谐音
  （如 Python→"派森"、GitHub→"吉特哈布"）；自动检测让模型可自由输出英文 token。
  若用户以纯中文为主，可在 config.json 把 asr.language 固定为 "zh"，换取语言一致性
  与略快速度（省去检测、无偶发误检）
- initial_prompt 热词：把 词库.txt 的词条拼进 initial_prompt，引导解码器优先输出专名/术语
- 幻觉抑制：no_speech_threshold / log_prob_threshold / compression_ratio_threshold 取
  faster-whisper 官方推荐默认（0.6 / -1.0 / 2.4），抑制静音幻觉与重复文本式幻觉
- 峰值归一化：转写前把音频峰值对齐到目标电平，避免过小声/过大声导致识别率下降
"""
import logging
import os
import sys
import threading

import numpy as np

# ================= 转写调优参数（集中收敛于此，便于整体调整） =================
DEFAULT_MODEL = "small"                   # 本地模型名/路径；切 medium 见 README（编排层负责下载）
DEFAULT_LANGUAGE = None                   # None=自动检测（中英混杂友好）；纯中文可设 "zh" 更稳
BEAM_SIZE = 8                             # 5→8：候选更宽，中文选词更准（速度略降，4060 可接受）
CONDITION_ON_PREVIOUS_TEXT = True         # 整段连贯解码；True 时前段错误可能向后传播，与 VAD 分段配合使用
NO_SPEECH_THRESHOLD = 0.6                 # 段 no_speech 概率超阈值 → 判为静音丢弃（官方推荐 0.6）
LOG_PROB_THRESHOLD = -1.0                 # 段平均对数概率低于阈值 → 判为低置信丢弃（官方推荐 -1.0）
COMPRESSION_RATIO_THRESHOLD = 2.4         # 压缩比超阈值 → 判为重复文本式幻觉，触发更高温度重解码（官方推荐 2.4）
USE_HOTWORDS = False                      # 备选实验：faster-whisper≥1.1.0 的 hotwords 参数，比 initial_prompt
                                          # 更硬性地抬高热词概率；与 beam_size>1 的配合需本机实测后再开
INITIAL_PROMPT_HEAD = "以下是普通话的句子。"  # initial_prompt 引导语：锚定中文语境
INITIAL_PROMPT_MAX_CHARS = 800            # 词库拼入上限：防超大词库拖慢解码（截断只影响提示，不影响功能）
NORMALIZE_TARGET_PEAK = 0.95              # 峰值归一化目标电平（留 0.05 余量防削波）
NORMALIZE_MIN_PEAK = 0.5                  # 峰值已高于该值则不动（避免过度放大底噪）
NORMALIZE_MIN_RMS = 1e-3                  # 整体 RMS 低于该值视为近静音底噪，不做放大
                                          # （否则 peak≈1e-4 的底噪会被放大 ~9500 倍成"内容"）
# =============================================================================


def _nvidia_dll_dirs():
    """定位 nvidia pip 包（nvidia-cublas-cu12 / nvidia-cudnn-cu12）的 DLL 目录，去重保序。

    设计原因：仅按 sys.path 中是否含 "site-packages" 字样的启发式会漏掉
    conda 环境、editable/解包安装、自定义前缀等非标准布局。这里优先用
    importlib.util.find_spec 定位 nvidia.cublas / nvidia.cudnn 包的实际安装
    位置（bin 目录在包目录的上级），定位失败再回退按 sys.path 扫描，兼容老布局。
    """
    import importlib.util

    seen = set()
    dirs = []

    def _add(d):
        d = os.path.abspath(d)
        if os.path.isdir(d) and d not in seen:
            seen.add(d)
            dirs.append(d)

    # 方案一：定位 nvidia.cublas / nvidia.cudnn 包位置（其 bin 在包目录的上级）
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError, AttributeError):
            spec = None
        if spec and spec.submodule_search_locations:
            for loc in spec.submodule_search_locations:
                _add(os.path.join(loc, "..", "bin"))
    # 方案二：回退按 sys.path 扫描（兼容未安装 nvidia 元包的布局）
    for sp in sys.path:
        if "site-packages" not in sp:
            continue
        for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
            _add(os.path.join(sp, sub))
    return dirs


def _add_nvidia_dll_paths():
    """把 pip 安装的 CUDA 运行库目录补进 PATH（须在 import faster_whisper 之前调用）。

    设计原因：faster-whisper 通过 ctranslate2 加载 GPU 库，nvidia-* pip 包
    （如 nvidia-cublas-cu12、nvidia-cudnn-cu12）通常把 DLL 放在
    site-packages/nvidia/<库名>/bin 下，而 ctranslate2 依赖 PATH 查找
    cublas64_12.dll 等；机器有显卡但缺 CUDA 运行库时，不加 PATH 会直接报
    `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded`。
    """
    import glob as _glob

    current = os.environ.get("PATH", "")
    for dll_dir in _nvidia_dll_dirs():
        # 只追加确实包含目标 DLL 的目录：避免把空/过时目录（如元包已卸载后
        # 残留的旧路径）加进 PATH，让 ctranslate2 徒劳搜索
        if not (_glob.glob(os.path.join(dll_dir, "cublas64_*.dll"))
                or _glob.glob(os.path.join(dll_dir, "cudnn64_*.dll"))):
            continue
        if dll_dir not in current:
            os.environ["PATH"] = dll_dir + os.pathsep + current
            current = os.environ["PATH"]


def _cuda_libs_ready() -> bool:
    """预检 CUDA 运行库是否可用（cublas64_12.dll + cudnn64_*.dll）。

    设计原因：ctranslate2 在 Windows 上加载 GPU 库时，若 DLL 缺失可能长时间
    挂起而非快速报错；先检查 DLL 存在再决定是否尝试 GPU，可保证缺库时
    立即走 CPU，绝不让用户干等。
    """
    import glob as _glob

    def _find(dll_pattern):
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if p and _glob.glob(os.path.join(p, dll_pattern)):
                return True
        for dll_dir in _nvidia_dll_dirs():
            if _glob.glob(os.path.join(dll_dir, dll_pattern)):
                return True
        return False

    return _find("cublas64_12.dll") and _find("cudnn64_*.dll")


def _is_gpu_error(error) -> bool:
    """判断异常是否与 GPU/CUDA 运行相关（决定是否触发推理时 GPU→CPU 回退）。

    设计原因：推理时回退会永久销毁已加载的 GPU 模型（self.model = None 后重载
    CPU），因此只能对 CUDA/ctranslate2 运行库类错误触发；音频内容错误
    （如 malformed 音频的 ValueError）与 GPU 无关，回退只会掩盖真实根因。
    同时检查异常链（__cause__），ctranslate2/faster-whisper 常把底层 CUDA
    异常包装为 RuntimeError 并挂上 cause。
    """
    signatures = ("cuda", "cublas", "cudnn", "ctranslate2")
    node = error
    while node is not None:
        msg = str(node).lower()
        if any(sig in msg for sig in signatures):
            return True
        node = getattr(node, "__cause__", None)
    return False


# 模块加载即执行：早于 main.py 等任何 `from faster_whisper import ...` 调用
_add_nvidia_dll_paths()


class WhisperEngine:
    def __init__(self, model=DEFAULT_MODEL, language=DEFAULT_LANGUAGE, words_path=None):
        self.model_name = model
        self.language = language
        self.words_path = words_path          # 词库路径；None 时默认取本文件同目录 词库.txt
        self.model = None
        self.device = "cpu"
        # GPU 回退原因（如"GPU 不可用已回退 CPU"），供 UI 展示可读错误
        self._gpu_fallback_reason = ""
        # v5.11：运行中 GPU 推理失败后置位，_load() 不再重试 GPU，避免反复崩溃
        self._gpu_disabled = False
        # 词库与 initial_prompt 的懒加载缓存（进程内生效；运行中修改词库需重启）
        self._glossary_loaded = False       # 无论词库是否为空都只读一次
        self._glossary_terms = []
        self._glossary_mappings = []
        self._initial_prompt = None
        # 懒加载路径（_load/_load_glossary/_initial_prompt_text）可能被 warmup（daemon 线程）、
        # draft 线程、_process worker 线程并发调用：check-then-act 竞态会导致双份模型/词库，
        # 用可重入锁守护（_initial_prompt_text 内部会再调 _load_glossary，故需 RLock）
        self._load_lock = threading.RLock()

    # ---------- 词库热词 ----------
    def _load_glossary(self):
        """读取 词库.txt → (terms, mappings)，全链路容错：文件缺失/编码错误/行格式异常都不影响转写。

        词库格式：每行一个词条，或 `原词=指定写法`（如 配森=Python）。
        这里直接读文件（也可换成 from config import load_words，结果一致）。
        只有读取成功才置 _glossary_loaded：文件瞬时不可读（I/O 错误/编码错误）
        时保持未加载，后续转写会重试，而不是静默空词库一辈子。

        v5.11：先读入局部列表、全部成功后整体替换，避免"读取中途失败→重试"
        时对已部分追加的列表再次追加，产生重复词条。
        """
        with self._load_lock:
            if self._glossary_loaded:
                return
            path = self.words_path or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "词库.txt"
            )
            if not os.path.exists(path):
                return  # 词库不存在 → 空热词，转写照常
            terms, mappings = [], []
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k and v:
                                mappings.append((k, v))
                        elif line:
                            terms.append(line)
            except (OSError, UnicodeDecodeError):
                # 记日志便于诊断；_glossary_loaded 保持 False → 下次调用重试，
                # 不把"读不了词库"永久固化（原实现静默吞掉且永不重试）
                logging.warning(
                    "词库 %s 读取失败，本次回退空热词（下次转写会重试）：", path,
                    exc_info=True,
                )
                return
            self._glossary_terms = terms
            self._glossary_mappings = mappings
            self._glossary_loaded = True

    def _initial_prompt_text(self):
        """把词库拼进 initial_prompt（结果缓存，进程内有效）：
        - 词条（如 GitHub、喵酱）：直接列出 → 引导解码器优先输出该词
        - 原词=写法（如 配森=Python）：给出对照关系 → 听到"配森"时更倾向输出 Python
        """
        with self._load_lock:
            if self._initial_prompt is None:
                self._load_glossary()
                if not self._glossary_loaded:
                    # v5.14：词库读取失败时不缓存空提示词，下次转写会重试
                    return None
                parts = [INITIAL_PROMPT_HEAD]
                if self._glossary_terms:
                    parts.append("术语：" + "、".join(self._glossary_terms))
                if self._glossary_mappings:
                    parts.append(
                        "写法对照：" + "；".join(
                            "{}={}".format(k, v) for k, v in self._glossary_mappings
                        )
                    )
                prompt = " ".join(parts)
                if len(prompt) > INITIAL_PROMPT_MAX_CHARS:
                    prompt = prompt[:INITIAL_PROMPT_MAX_CHARS]
                self._initial_prompt = prompt
            return self._initial_prompt

    # ---------- 音频预处理 ----------
    @staticmethod
    def _normalize_audio(audio):
        """峰值归一化：把音频峰值对齐到 NORMALIZE_TARGET_PEAK。

        过小声（峰值 < 0.1）时特征过弱、识别率明显下降；过大声可能削波失真。
        峰值已接近满幅（≥ NORMALIZE_MIN_PEAK）或接近纯静音（峰值 < 1e-6）时不动。
        仅凭峰值判断仍会把"峰值 1e-4 的底噪"放大 ~9500 倍成内容，故再叠加
        RMS 门槛（NORMALIZE_MIN_RMS）：整段能量过低说明是底噪/稀疏尖峰而非
        语音内容，同样不做调整，避免把底噪放大成"内容"。
        """
        audio = np.asarray(audio, dtype=np.float32)
        if audio.size == 0:
            return audio
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(np.max(np.abs(audio)))
        if peak < 1e-6 or NORMALIZE_MIN_PEAK <= peak <= 1.0:
            return audio  # 纯静音或电平已合适：不做调整
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        if rms < NORMALIZE_MIN_RMS:
            return audio  # 整体能量过低 → 底噪/稀疏尖峰而非内容：不做调整
        gain = NORMALIZE_TARGET_PEAK / peak
        return np.clip(audio * gain, -1.0, 1.0)

    # ---------- 模型加载与推理（保留原有 CUDA 预检/回退逻辑） ----------
    def _load(self):
        # 锁内整体加载：warmup(daemon 线程) 与转写线程并发调用时，check-then-act 竞态
        # 会导致双份 WhisperModel（GPU 双倍显存/OOM）；锁保证只加载一次
        with self._load_lock:
            if self.model is not None:
                return
            from faster_whisper import WhisperModel
            if self._gpu_disabled or not _cuda_libs_ready():
                # 已回退过 CPU 或 CUDA 运行库缺失：直接走 CPU，
                # 避免 ctranslate2 在缺 DLL 时构造 GPU 模型挂起 / 回退后再崩溃
                if not self._gpu_disabled:
                    self._gpu_fallback_reason = "CUDA 运行库未安装（缺 cublas/cudnn），已用 CPU 模式"
                try:
                    self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                    self.device = "cpu"
                except Exception as e2:
                    raise RuntimeError("模型加载失败（CPU）：{}".format(e2)) from e2
                return
            try:
                # GPU 优先：RTX 4060 等显卡可用时速度快得多
                self.model = WhisperModel(self.model_name, device="cuda", compute_type="float16")
                self.device = "cuda"
            except Exception as e:
                # CUDA 初始化失败（缺运行库/驱动/显存不足等）→ 干净回退 CPU(int8)，绝不裸抛崩溃
                self._gpu_fallback_reason = "GPU 不可用已回退 CPU（{}）".format(e)
                try:
                    self.model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                    self.device = "cpu"
                except Exception as e2:
                    # 模型下载失败/不存在等：抛可读异常，UI 可直接展示；
                    # 错误链同时保留 GPU 失败原因，便于诊断缺驱动/缺库/显存不足
                    raise RuntimeError(
                        "模型加载失败（已尝试 GPU 与 CPU）：GPU: {}; CPU: {}".format(e, e2)
                    ) from e2

    def _fallback_to_cpu(self, error):
        """推理时 GPU 不可用（如运行中才暴露的 DLL 崩溃）→ 替换为 CPU(int8) 模型。

        v5.11 竞态修复：换模型全程持锁，且新模型构造成功后才整体替换 self.model，
        绝不把 self.model 置 None——并发线程要么读到旧 GPU 模型、要么读到新 CPU 模型，
        两者都是有效模型对象，杜绝 `None.transcribe` 崩溃。
        """
        from faster_whisper import WhisperModel

        with self._load_lock:
            if self.device == "cpu":
                return
            self._gpu_fallback_reason = "GPU 不可用已回退 CPU（{}）".format(error)
            self._gpu_disabled = True
            try:
                new_model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            except Exception as e2:
                # CPU 也加载失败：允许下次 _load 再尝试 GPU（重置标志），异常带可读上下文
                self._gpu_disabled = False
                raise RuntimeError(
                    "模型加载失败（已尝试 GPU 与 CPU）：GPU: {}; CPU: {}".format(error, e2)
                ) from e2
            self.model = new_model
            self.device = "cpu"

    def _transcribe_once(self, audio, use_vad):
        """单次转写：参数集中于模块常量，改动一处全局生效。"""
        audio = self._normalize_audio(audio)
        kwargs = dict(
            language=self.language,               # None=自动检测；"zh"=固定中文
            beam_size=BEAM_SIZE,
            condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
            no_speech_threshold=NO_SPEECH_THRESHOLD,
            log_prob_threshold=LOG_PROB_THRESHOLD,
            compression_ratio_threshold=COMPRESSION_RATIO_THRESHOLD,
            initial_prompt=self._initial_prompt_text(),
            vad_filter=use_vad,
        )
        if USE_HOTWORDS:
            # faster-whisper ≥1.1.0 原生热词：比 initial_prompt 更强硬，默认关闭（见常量注释）
            kwargs["hotwords"] = list(self._glossary_terms) + [
                v for _, v in self._glossary_mappings
            ]
        segments, _ = self.model.transcribe(audio, **kwargs)
        return "".join(s.text for s in segments).strip()

    def transcribe(self, audio: np.ndarray) -> str:
        self._load()
        if audio is None or len(audio) == 0:
            return ""
        try:
            return self._transcribe_once(audio, use_vad=True)
        except Exception as e:
            # 推理异常：仅当确实是 CUDA/ctranslate2 运行库错误时才回退 CPU 重试
            # （回退会销毁已加载的 GPU 模型，非 GPU 错误（如坏音频的 ValueError）
            # 触发回退会永久降级 CPU 并掩盖真实根因）；VAD 异常时去掉 VAD 再试。
            # 被吞掉的中间错误全部记日志：原实现静默丢弃，会掩盖真实缺陷且难以复现
            if self.device == "cuda" and _is_gpu_error(e):
                self._fallback_to_cpu(e)
                try:
                    return self._transcribe_once(audio, use_vad=True)
                except Exception as e2:
                    logging.warning(
                        "GPU→CPU 回退后转写仍失败（继续关闭 VAD 重试）：%s", e2,
                        exc_info=True,
                    )
            try:
                return self._transcribe_once(audio, use_vad=False)
            except Exception as e2:
                # 兜底：抛带可读上下文的异常（含 GPU 回退原因），UI 可显示"转写失败：原因"
                hint = self._gpu_fallback_reason or "转写失败（设备 {}）".format(self.device)
                raise RuntimeError("{}：{}".format(hint, e2)) from e2

    def warmup(self):
        """后台预热：提前加载模型，避免第一次使用时才下载/加载；异常不抛出但记日志。"""
        try:
            self._load()
        except Exception:
            logging.warning("模型预热失败（首次转写时会重试）：", exc_info=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # v5.13.6：GBK 控制台兼容
    # 快速自检（不加载模型、不联网）：打印当前转写参数与词库热词拼装结果，验证归一化逻辑
    engine = WhisperEngine()
    prompt = engine._initial_prompt_text()
    print("模型:", engine.model_name, "| 语言:", engine.language or "自动检测（中英混杂友好）")
    print("beam_size:", BEAM_SIZE, "| condition_on_previous_text:", CONDITION_ON_PREVIOUS_TEXT)
    print(
        "幻觉抑制: no_speech={} log_prob={} compression_ratio={}".format(
            NO_SPEECH_THRESHOLD, LOG_PROB_THRESHOLD, COMPRESSION_RATIO_THRESHOLD
        )
    )
    print("词库词条:", len(engine._glossary_terms), "| 写法映射:", len(engine._glossary_mappings))
    print("initial_prompt:", prompt)
    t = np.linspace(0, 1, 16000, dtype=np.float32)
    tiny = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    out = engine._normalize_audio(tiny)
    print(
        "归一化自检: 峰值 {:.3f} → {:.3f}（目标 {:.2f}）".format(
            float(np.max(np.abs(tiny))), float(np.max(np.abs(out))), NORMALIZE_TARGET_PEAK
        )
    )
    silent = np.zeros(16000, dtype=np.float32)
    print("静音保护自检: 纯静音不做放大 =", np.array_equal(silent, engine._normalize_audio(silent)))
