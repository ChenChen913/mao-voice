"""
语音活动检测（Voice Activity Detection）模块 —— 基于能量阈值的 VAD。

纯 Python + numpy，零额外依赖。输入 16kHz float32 单声道音频帧，
通过 RMS/dB 能量阈值 + 去抖状态机判断「说话/静音」。

使用示例:
    vad = VAD(threshold_db=-35.0, min_speech_ms=120, min_silence_ms=200)
    vad.process(audio_frame)          # np.ndarray 或 bytes (float32)
    if vad.is_speaking(): ...
    if vad.silence_seconds() > 2.0:   # 静音超过 2 秒
        ...

阈值参考:
    -40 dB  灵敏 — 轻声/远场也能触发，但易受环境噪音干扰
    -35 dB  适中 — 桌面近场麦克风推荐默认值
    -30 dB  严格 — 只对明显讲话能量响应
    -25 dB  苛刻 — 几乎只有大声说话才触发
"""

import threading

import numpy as np


# ---------------------------------------------------------------------------
# 可调参数常量 — 修改这里即可全局生效
# ---------------------------------------------------------------------------

# 采样率（Hz），必须与录音模块保持一致
SAMPLE_RATE: int = 16000

# 默认能量阈值（dB）。RMS 能量低于此值视为静音。
# 浮点音频归一化到 [-1, 1] 区间，dB = 20 * log10(RMS).
# 典型桌面麦克风近距离录音，-35 dB 是合理的起点。
DEFAULT_THRESHOLD_DB: float = -35.0

# 最短说话时长（ms）：高能量帧必须持续至少这么久才确认进入"说话"状态。
# 防止短促噪音（键盘敲击、咳嗽）误触发。
DEFAULT_MIN_SPEECH_MS: int = 120

# 最短静音时长（ms）：低能量帧必须持续至少这么久才确认进入"静音"状态。
# 防止说话中自然停顿（换气、句间停顿）被误判为结束。
DEFAULT_MIN_SILENCE_MS: int = 200

# 避免 log10(0) 的微小值
_EPS: float = 1e-10


class VAD:
    """基于能量阈值的语音活动检测器。

    内部维护一个二态状态机：
      - 静音态 (is_speaking=False)
      - 说话态 (is_speaking=True)

    状态转移有去抖（debounce）保护：
      - 静音→说话：需连续高能量样本数 ≥ min_speech_samples
      - 说话→静音：需连续低能量样本数 ≥ min_silence_samples
    """

    def __init__(
        self,
        threshold_db: float = DEFAULT_THRESHOLD_DB,
        min_speech_ms: int = DEFAULT_MIN_SPEECH_MS,
        min_silence_ms: int = DEFAULT_MIN_SILENCE_MS,
    ):
        """初始化 VAD 检测器。

        Args:
            threshold_db: 能量阈值（dB）。低于此值的帧视为静音。
            min_speech_ms: 最短说话时长（ms）。短于此值的高能量视为噪音。
            min_silence_ms: 最短静音时长（ms）。短于此值的低能量视为句间停顿。
        """
        self.threshold_db = float(threshold_db)
        self.min_speech_samples: int = max(
            1, int(min_speech_ms * SAMPLE_RATE / 1000)
        )
        self.min_silence_samples: int = max(
            1, int(min_silence_ms * SAMPLE_RATE / 1000)
        )

        # ---- 内部状态 ----
        self._state: bool = False          # False=静音, True=说话
        self._consecutive_speech: int = 0  # 连续高能量样本数
        self._consecutive_silence: int = 0 # 连续低能量样本数
        self._total_samples: int = 0       # 累计处理样本总数
        # 当前静音段起始样本索引；None 表示尚未发生任何"说话→静音"转移
        # （silence_seconds() 在首次转移前返回 0.0，不把会话全程时长当静音时长）
        self._silence_start_sample: int | None = None

        # 最近一帧的 dB 值（调试/观测用）：内部值只在锁下读写，
        # 外部通过 last_db 属性读取（带锁），遵守类声明的线程安全契约
        self._last_db: float = -100.0

        # 线程安全：process/reset 在 sounddevice 回调线程调用，
        # is_speaking/silence_seconds 在主线程/GUI 线程读取；
        # 无锁时读线程可能观察到写线程的半更新状态（撕裂读），导致误判
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def process(self, frame) -> None:
        """累积处理一帧音频。

        Args:
            frame: bytes (raw float32 PCM) 或 numpy.ndarray (dtype=float32).
                   空帧（size=0）、长度非 4 字节倍数的 bytes、无法转为 float32
                   的输入都会被安全忽略（绝不抛异常）。
        """
        # 统一转为 float32 numpy 数组；畸形输入安全忽略
        if isinstance(frame, bytes):
            if len(frame) % 4 != 0:
                return  # 长度不是 float32 字节数的整数倍 → 畸形帧（numpy≥1.24 会抛 ValueError）
            frame = np.frombuffer(frame, dtype=np.float32)
        else:
            try:
                frame = np.asarray(frame, dtype=np.float32)
            except Exception:
                return  # 标量/无法转换的对象 → 忽略
        n_samples = frame.size
        if n_samples == 0:
            return

        with self._lock:
            # 计算当前帧的 RMS 能量 (dB)
            db = self._compute_db(frame)

            # 更新累计样本计数
            self._total_samples += n_samples

            if db >= self.threshold_db:
                # ---- 高能量帧：疑似语音 ----
                self._consecutive_speech += n_samples
                self._consecutive_silence = 0

                # 静音态 + 连续高能量超过最短说话时长 → 进入说话态
                if not self._state and self._consecutive_speech >= self.min_speech_samples:
                    self._state = True

            else:
                # ---- 低能量帧：疑似静音 ----
                self._consecutive_silence += n_samples
                self._consecutive_speech = 0

                # 说话态 + 连续低能量超过最短静音时长 → 进入静音态
                if self._state and self._consecutive_silence >= self.min_silence_samples:
                    self._state = False
                    # 记录静音起点：回退到首次触发静音的那一帧开头
                    self._silence_start_sample = (
                        self._total_samples - self._consecutive_silence
                    )

            self._last_db = db

    def is_speaking(self) -> bool:
        """返回当前是否处于说话状态。"""
        with self._lock:
            return self._state

    @property
    def last_db(self) -> float:
        """最近一帧的 dB 值（调试/观测用）。

        回调线程写、观测线程读：必须走锁，直接读公开属性会绕过
        类声明的线程安全契约（冒烟测试等读方一律经此属性）。
        """
        with self._lock:
            return self._last_db

    def silence_seconds(self) -> float:
        """返回当前连续静音的时长（秒）。

        说话中返回 0.0；静音中返回从说话结束到现在的时长。
        从未说过话（尚无"说话→静音"转移）时返回 0.0：不能把会话开始至今
        的全程时长当作"静音时长"——它没有锚定任何真实的语音边界，会让
        "静音超 N 秒自动停止"在用户开口前就倒计时。
        """
        with self._lock:
            if self._state or self._silence_start_sample is None:
                return 0.0
            return (self._total_samples - self._silence_start_sample) / SAMPLE_RATE

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_db(frame: np.ndarray) -> float:
        """计算 float32 音频帧的 RMS 能量 (dB)。

        float32 归一化到 [-1, 1]：
            RMS = sqrt(mean(sample^2))
            dB  = 20 * log10(RMS + ε)
        """
        # 用 float64 累积平方和，避免 float32 精度不足
        rms = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
        if not np.isfinite(rms):
            # Inf/NaN 输入按静音处理：Inf 会让 dB=inf 永远被判为说话，
            # NaN 走 max() 落到 _EPS 判为 -200dB 深静音——行为不一致，统一按静音
            return -100.0
        return 20.0 * np.log10(max(float(rms), _EPS))

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置内部状态，等效于重新创建一个 VAD 实例。"""
        with self._lock:
            self._state = False
            self._consecutive_speech = 0
            self._consecutive_silence = 0
            self._total_samples = 0
            self._silence_start_sample = None
            self._last_db = -100.0

    def __repr__(self) -> str:
        with self._lock:
            state = "SPEAKING" if self._state else "SILENT"
            last_db = self._last_db
        return (
            f"VAD(threshold={self.threshold_db:.1f} dB, "
            f"speech≥{self.min_speech_samples} samples, "
            f"silence≥{self.min_silence_samples} samples, "
            f"state={state}, "
            f"last_db={last_db:.1f})"
        )


# ===================================================================
# 冒烟测试
# ===================================================================
if __name__ == "__main__":
    sr = SAMPLE_RATE
    vad = VAD()

    # 构造测试音频
    silence_500ms = np.zeros(sr // 2, dtype=np.float32)               # 500 ms 静音
    loud_speech = (np.random.randn(sr).astype(np.float32) * 0.3)     # 1 s 高能量噪音（模拟语音）

    print("=== VAD 冒烟测试 ===\n")

    # 测试 1: 纯静音应保持静音态
    vad.process(silence_500ms)
    assert not vad.is_speaking(), "纯静音应判为静音"
    print(f"[OK] 500ms 静音:  is_speaking={vad.is_speaking()}, silence={vad.silence_seconds():.3f}s")

    # 测试 2: 连续高能量应触发说话态
    vad.process(loud_speech)
    assert vad.is_speaking(), "1s 高能量应判为说话"
    print(f"[OK] 1s 高能量:   is_speaking={vad.is_speaking()}, silence={vad.silence_seconds():.3f}s")

    # 测试 3: 说话后短暂静音不应退出（min_silence_ms=200ms 保护）
    vad.process(silence_500ms[:sr // 10])  # 100ms 静音
    assert vad.is_speaking(), "100ms 静音不应退出说话态"
    print(f"[OK] 100ms 停顿:  is_speaking={vad.is_speaking()}  (仍为 True，去抖保护生效)")

    # 测试 4: 说话后足够长静音应退出
    vad.process(silence_500ms)  # 再加 500ms 静音，累计 > 200ms
    assert not vad.is_speaking(), "累计 >200ms 静音应退出说话态"
    print(f"[OK] +500ms 静音:  is_speaking={vad.is_speaking()}, silence={vad.silence_seconds():.3f}s")

    # 测试 5: 短促噪音不应触发（min_speech_ms=120ms 保护）
    vad2 = VAD()
    short_noise = loud_speech[:sr // 20]  # 50ms 噪音
    vad2.process(short_noise)
    assert not vad2.is_speaking(), "50ms 噪音不应触发说话态"
    print(f"[OK] 50ms 噪音:   is_speaking={vad2.is_speaking()}  (仍为 False，去抖保护生效)")

    # 测试 6: bytes 输入支持
    vad3 = VAD()
    raw_bytes = loud_speech.tobytes()
    vad3.process(raw_bytes)
    print(f"[OK] bytes 输入:  is_speaking={vad3.is_speaking()}, last_db={vad3.last_db:.1f}")

    # 测试 7: 重置后状态清零
    vad3.reset()
    assert not vad3.is_speaking()
    assert vad3.silence_seconds() == 0.0
    print(f"[OK] reset():      is_speaking={vad3.is_speaking()}, silence={vad3.silence_seconds():.3f}s")

    print("\n=== 全部测试通过 ===")
