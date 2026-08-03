# -*- coding: utf-8 -*-
"""
云端 ASR 兜底引擎（cloud_asr）

对接 OpenAI 兼容的 /v1/audio/transcriptions 接口（如智谱 GLM-ASR、
硅基流动、MiniMax、OpenAI 官方等），作为本地 faster-whisper 引擎的
兜底方案：本地 GPU 不可用、识别准确率或速度不达标时切换到本引擎。

与本地引擎（../../asr.py 的 WhisperEngine）输入对齐：
transcribe 接收 16kHz float32 mono numpy 数组，内部转成标准 WAV 字节后
以 multipart/form-data 上传。

仅依赖：Python 标准库 + numpy + requests
"""

import io
import wave
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import requests

# 上传时的音频文件名（部分端点依据扩展名判断格式，必须带 .wav）
_WAV_FILENAME = "audio.wav"
_WAV_MIME = "audio/wav"
# 请求超时（秒）：云端网络不稳定，给足时间避免误判失败
_REQUEST_TIMEOUT = 120.0


def _safe_url(url: str) -> str:
    """去掉 URL 的 query/userinfo，避免错误信息泄露潜在凭证（v5.11）。"""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


class CloudASREngine:
    """OpenAI 兼容 /v1/audio/transcriptions 端点的轻量客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str = "whisper-1"):
        """
        :param base_url: 端点根地址，如 "https://api.openai.com/v1"。
            内部会拼成 {base_url}/audio/transcriptions，允许带或不带结尾斜杠。
        :param api_key: 厂商 API Key；为空时调用 transcribe 会直接抛错。
        :param model: 语音识别模型名，默认 "whisper-1"（OpenAI 官方默认）。
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = model

    def _audio_to_wav(self, audio) -> bytes:
        """
        把 16kHz float32 mono numpy 数组编码为标准 WAV 字节。

        约定（与本地引擎输入一致）：
        - 采样率固定 16000 Hz
        - 单声道（若传入多声道则沿通道轴取平均，兼容立体声输入）
        - 16-bit PCM（sampwidth=2），可被标准 wave 模块读回

        关键决策：若调用方传入的是 int16 PCM 数组（如直接从音频文件
        读出的整数采样），直接按 float32 处理会把 [-32768, 32767] 当成
        [-1, 1] 导致声音爆音，因此先按 dtype 归一化到 [-1, 1] 再量化。
        """
        audio_arr = np.asarray(audio)
        # 空音频快速失败：零长度或极短（<10ms）的音频绝大多数 ASR 引擎无法识别，
        # 直接本地报错而非依赖远端端点的不可靠响应。
        if audio_arr.size == 0:
            raise ValueError("音频数据为空，无法编码为 WAV")
        min_samples = int(16000 * 0.01)  # 10ms
        if audio_arr.size < min_samples:
            raise ValueError(
                f"音频数据过短：{audio_arr.size} 采样点（{audio_arr.size / 16000:.3f}s），"
                f"最少需要 {min_samples} 采样点（10ms）"
            )
        # 整型输入归一化到 [-1, 1]；float 输入假定已在 [-1, 1]
        if np.issubdtype(audio_arr.dtype, np.integer):
            info = np.iinfo(audio_arr.dtype)
            audio_f = (audio_arr.astype(np.float32) - float(info.min)) / (float(info.max) - float(info.min)) * 2.0 - 1.0
        else:
            audio_f = audio_arr.astype(np.float32)
        # 多声道取平均转单声道（含尾部单通道列的情况）
        if audio_f.ndim > 1:
            audio_f = audio_f.mean(axis=1)
        # 裁剪越界值并量化为 16-bit 有符号整数（四舍五入避免截断偏移）
        pcm = np.clip(audio_f, -1.0, 1.0)
        # 关键：修复 NaN 值。np.clip 对 NaN 无效，NaN→int16 行为未定义
        # （NumPy ≥2 产生 RuntimeWarning 且输出 INT16_MIN/0），产生爆音。
        # 用 nan_to_num 替代 NaN 为 0.0，确保量化行为确定性。
        pcm = np.nan_to_num(pcm, nan=0.0)
        pcm = np.round(pcm * 32767.0).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit = 2 字节
            wf.setframerate(16000)
            wf.writeframes(pcm.tobytes())
        return buf.getvalue()

    def transcribe(self, audio, language: str = "zh") -> str:
        """
        识别音频，返回识别文本。

        :param audio: 16kHz float32 mono numpy 数组（与本地 WhisperEngine 输入一致）。
        :param language: 语言代码，默认 "zh"；传入空串/None 时不发送该字段，
            由端点自动检测（部分端点不支持该字段时也能正常调用）。
        :raises RuntimeError: 未配置 api_key、网络请求失败、端点返回非 2xx、
            响应解析失败或缺少 text 字段时抛出，异常信息含可排查的上下文。
        :return: 识别出的文本。
        """
        # 关键决策：api_key 为空必须显式报错而非静默返回空串，
        # 否则上游会把"空结果"当成正常识别结果提交给用户，掩盖配置问题。
        if not self.api_key:
            raise RuntimeError(
                "CloudASREngine 未配置 api_key：请在初始化时提供有效的 api_key，"
                "例如 CloudASREngine(base_url=..., api_key=os.environ['ASR_API_KEY'])。"
            )

        files = {"file": (_WAV_FILENAME, self._audio_to_wav(audio), _WAV_MIME)}
        data = {"model": self.model}
        if language:
            data["language"] = language
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"{self.base_url}/audio/transcriptions"

        # 网络层异常（DNS 失败、连接拒绝、超时等）统一转成带 URL 的明确错误
        try:
            resp = requests.post(
                url, headers=headers, files=files, data=data, timeout=_REQUEST_TIMEOUT
            )
        except requests.RequestException as e:
            raise RuntimeError(f"请求云端 ASR 端点失败（{_safe_url(url)}）：{e}") from e

        if not (200 <= resp.status_code < 300):
            raise RuntimeError(
                f"云端 ASR 端点返回非 2xx 状态码 {resp.status_code}（{_safe_url(url)}）："
                f"{resp.text[:500]}"
            )

        # 解析 OpenAI 兼容响应 {"text": "..."}；解析失败或缺少 text 也报错
        try:
            payload = resp.json()
        except ValueError as e:
            raise RuntimeError(
                f"解析云端 ASR 响应 JSON 失败（{_safe_url(url)}）：{e}；原始响应：{resp.text[:500]}"
            ) from e
        try:
            text = payload.get("text")
        except AttributeError as e:
            raise RuntimeError(
                f"云端 ASR 响应 JSON 解析成功但结果不是对象（{_safe_url(url)}）：{type(payload).__name__}；"
                f"原始响应：{resp.text[:500]}"
            ) from e

        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(
                f"云端 ASR 响应缺少非空 text 字段（{_safe_url(url)}）：{str(payload)[:300]}"
            )
        return text


if __name__ == "__main__":
    # 冒烟测试：不依赖真实网络，验证 WAV 编码与无 key 报错逻辑
    sr = 16000
    t = np.linspace(0, 0.5, int(sr * 0.5), endpoint=False)
    demo_audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    engine = CloudASREngine(base_url="https://example.com/v1", api_key="")

    # 1) 生成的 WAV 必须能被 wave 读回，且采样率 16000、单声道、16-bit
    wav_bytes = engine._audio_to_wav(demo_audio)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == 16000, wf.getframerate()
        assert wf.getnchannels() == 1, wf.getnchannels()
        assert wf.getsampwidth() == 2, wf.getsampwidth()
        assert wf.getnframes() == len(demo_audio), wf.getnframes()
    print("[OK] _audio_to_wav 生成 16000Hz / 单声道 / 16-bit 标准 WAV，可被 wave 读回")

    # 2) 未配置 api_key 时 transcribe 必须抛可读异常
    try:
        engine.transcribe(demo_audio)
    except RuntimeError as e:
        print(f"[OK] 无 api_key 报错符合预期：{e}")
    else:
        raise AssertionError("未配置 api_key 时 transcribe 应抛出异常")
