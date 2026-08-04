# -*- coding: utf-8 -*-
"""配置与词库单元测试（使用临时目录，不碰真实 config.json）。"""
import json
import os

import pytest

import config


def test_load_defaults_when_missing(tmp_path):
    cfg = config.load_config(str(tmp_path / "nope.json"))
    assert cfg["hotkey"] == "alt_r"
    # v5.17（N-m4）：默认模型改为相对路径，load_config 会解析为绝对路径
    expected_model = os.path.normpath(
        os.path.join(config.BASE_DIR, "models", "faster-whisper-medium")
    )
    assert cfg["asr"]["model"] == expected_model
    assert cfg["asr"]["language"] is None
    # v5.16（C2）：隐私默认关闭
    assert config.DEFAULT_CONFIG["history"]["enabled"] is False
    assert cfg["history"]["enabled"] is False


def test_deep_merge(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"asr": {"model": "medium"}, "ui": {"max_chars": 99}}), encoding="utf-8")
    cfg = config.load_config(str(p))
    assert cfg["asr"]["model"] == "medium"
    assert cfg["asr"]["language"] is None
    assert cfg["ui"]["max_chars"] == 99


def test_corrupt_config_falls_back(tmp_path, caplog):
    p = tmp_path / "bad.json"
    p.write_text("{broken", encoding="utf-8")
    cfg = config.load_config(str(p))
    assert cfg["hotkey"] == "alt_r"
    assert any("读取/解析失败" in r.message for r in caplog.records)


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "c.json"
    cfg = {"hotkey": "f9", "asr": {"model": "medium"}, "ui": {"max_chars": 200}}
    config.save_config(cfg, str(p))
    assert config.load_config(str(p)) == {
        **config.DEFAULT_CONFIG,
        "hotkey": "f9",
        "asr": {**config.DEFAULT_CONFIG["asr"], "model": "medium"},
        "ui": {**config.DEFAULT_CONFIG["ui"], "max_chars": 200},
    }


def test_save_failure_cleans_tmp(tmp_path):
    bad = str(tmp_path / "no" / "c.json")
    with pytest.raises(OSError):
        config.save_config({"a": 1}, bad)
    assert not os.path.exists(bad + ".tmp")


def test_ensure_defaults_tolerant(tmp_path):
    bad_words = str(tmp_path / "no" / "dict.txt")
    config.ensure_defaults(str(tmp_path / "cfg.json"), bad_words)  # 不应抛异常


def test_load_words_formats(tmp_path):
    p = tmp_path / "词库.txt"
    p.write_text("# 注释\nGitHub\n配森=Python\n=空\n坏=\n", encoding="utf-8")
    terms, mappings = config.load_words(str(p))
    assert terms == ["GitHub"]
    assert mappings == [("配森", "Python")]


def test_build_words_block(tmp_path):
    p = tmp_path / "词库.txt"
    p.write_text("GitHub\n配森=Python\n", encoding="utf-8")
    block = config.build_words_block(str(p))
    assert "- GitHub" in block and "配森 → Python" in block


def test_resolve_keys_env_fallback_not_persisted(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"refine": {"api_key": ""}}), encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    cfg = config.load_config(str(p))
    refine_key, cloud_key = config.resolve_keys(cfg)
    assert refine_key == "sk-env"
    assert cloud_key == "sk-env"
    # v5.14：环境变量只参与运行时解析，不写回配置，避免被 save_config 持久化
    assert cfg["refine"]["api_key"] == ""


def test_relative_model_path_resolved(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"asr": {"model": "models/faster-whisper-small"}}), encoding="utf-8")
    cfg = config.load_config(str(p))
    expected = os.path.normpath(os.path.join(config.BASE_DIR, "models", "faster-whisper-small"))
    assert cfg["asr"]["model"] == expected
