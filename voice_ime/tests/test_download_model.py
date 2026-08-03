# -*- coding: utf-8 -*-
"""模型下载脚本单元测试：只验证 URL 构建与可读大小，不联网。"""
import download_model


def test_build_urls_modelscope():
    urls = download_model.build_urls("small", "modelscope")
    assert len(urls) == 4
    assert urls[0][0].startswith("https://modelscope.cn/models/Systran/faster-whisper-small/")
    assert urls[3][1] == "model.bin"


def test_build_urls_hf():
    urls = download_model.build_urls("medium", "hf")
    assert urls[0][0].startswith("https://huggingface.co/Systran/faster-whisper-medium/")


def test_human_size():
    assert download_model.human_size(0) == "0 B"
    assert "KB" in download_model.human_size(2048)
    assert "MB" in download_model.human_size(1024 * 1024 * 5)
