# -*- coding: utf-8 -*-
"""云端 ASR 单元测试：不联网。"""
import io
import wave

import numpy as np
import pytest

import cloud_asr


def _audio(sec=0.5, amp=0.2):
    t = np.linspace(0, sec, int(16000 * sec), endpoint=False)
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


def test_wav_encode_format():
    e = cloud_asr.CloudASREngine(base_url="https://x/v1", api_key="k")
    data = e._audio_to_wav(_audio())
    with wave.open(io.BytesIO(data), "rb") as wf:
        assert wf.getframerate() == 16000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2


def test_empty_audio_error():
    e = cloud_asr.CloudASREngine(base_url="https://x/v1", api_key="k")
    with pytest.raises(ValueError):
        e._audio_to_wav(np.empty(0, dtype=np.float32))


def test_missing_api_key_error():
    e = cloud_asr.CloudASREngine(base_url="https://x/v1", api_key="")
    with pytest.raises(RuntimeError, match="api_key"):
        e.transcribe(_audio())


def test_safe_url_strips_credentials():
    assert cloud_asr._safe_url("https://user:pass@host/v1?token=secret") == "https://host/v1"


def test_safe_url_ipv6():
    assert cloud_asr._safe_url("https://[::1]:8080/v1?token=secret") == "https://[::1]:8080/v1"


class _FakeResp:
    status_code = 200
    text = '{"text": "ok"}'

    def json(self):
        return {"text": "ok"}


def test_language_config_sent_and_auto_omitted(monkeypatch):
    """C5：实例 language 决定是否发送 language 字段；None=自动检测不发送。"""
    captured = []

    def fake_post(url, headers, files, data, timeout):
        captured.append(data)
        return _FakeResp()

    monkeypatch.setattr(cloud_asr.requests, "post", fake_post)
    audio = _audio()

    e_zh = cloud_asr.CloudASREngine("https://x/v1", "k", language="zh")
    e_zh.transcribe(audio)
    e_auto = cloud_asr.CloudASREngine("https://x/v1", "k", language=None)
    e_auto.transcribe(audio)
    e_override = cloud_asr.CloudASREngine("https://x/v1", "k", language="zh")
    e_override.transcribe(audio, language="en")

    assert captured[0]["language"] == "zh"
    assert "language" not in captured[1]
    assert captured[2]["language"] == "en"  # 显式传参覆盖实例配置
