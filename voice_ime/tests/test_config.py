# -*- coding: utf-8 -*-
"""配置与词库单元测试（使用临时目录，不碰真实 config.json）。"""
import json
import os

import pytest

import config


def test_load_defaults_when_missing(tmp_path):
    cfg = config.load_config(str(tmp_path / "nope.json"))
    assert cfg["hotkey"] == "alt_r"
    assert cfg["asr"]["model"] == "small"


def test_deep_merge(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"asr": {"model": "medium"}, "ui": {"max_chars": 99}}), encoding="utf-8")
    cfg = config.load_config(str(p))
    assert cfg["asr"]["model"] == "medium"
    assert cfg["asr"]["language"] == "zh"
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


def test_env_api_key_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"refine": {"api_key": ""}}), encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    cfg = config.load_config(str(p))
    assert cfg["refine"]["api_key"] == "sk-env"


def test_relative_model_path_resolved(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"asr": {"model": "models/faster-whisper-small"}}), encoding="utf-8")
    cfg = config.load_config(str(p))
    expected = os.path.normpath(os.path.join(config.BASE_DIR, "models", "faster-whisper-small"))
    assert cfg["asr"]["model"] == expected
