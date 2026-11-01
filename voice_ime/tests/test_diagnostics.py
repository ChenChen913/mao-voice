# -*- coding: utf-8 -*-
"""诊断报告脱敏测试。"""
import diagnostics


def test_report_masks_api_keys_and_includes_checks(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.json"):
        (model / name).write_bytes(b"x")

    cfg = {
        "asr": {"model": str(model), "engine": "whisper"},
        "refine": {"api_key": "SECRET-KEY", "base_url": "https://example.com"},
        "recorder": {"device": ""},
        "inject": {},
    }
    monkeypatch.setattr(diagnostics.doctor, "run", lambda: [("自检", True, "通过")])
    report = diagnostics.collect_report(cfg)

    assert "SECRET-KEY" not in report
    assert "已配置" in report
    assert "模型目录" in report
    assert "[通过] 自检" in report
