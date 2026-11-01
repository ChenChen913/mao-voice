# -*- coding: utf-8 -*-
"""模型目录校验与扫描单元测试。"""
import os

import model_store


def _make_model(path, vocab="vocabulary.json"):
    path.mkdir(parents=True, exist_ok=True)
    for name in ("model.bin", "config.json", "tokenizer.json", vocab):
        (path / name).write_bytes(b"x")


def test_validate_requires_core_files(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = model_store.validate_model_dir(str(empty))
    assert not result["ok"]
    assert "model.bin" in result["message"]


def test_validate_accepts_json_or_txt_vocabulary(tmp_path):
    with_json = tmp_path / "with-json"
    _make_model(with_json)
    assert model_store.validate_model_dir(str(with_json))["ok"]

    with_txt = tmp_path / "with-txt"
    _make_model(with_txt, vocab="vocabulary.txt")
    assert model_store.validate_model_dir(str(with_txt))["ok"]


def test_validate_missing_vocabulary_is_reported(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (model / name).write_bytes(b"x")
    result = model_store.validate_model_dir(str(model))
    assert not result["ok"]
    assert "vocabulary" in result["message"]


def test_resolve_relative_path_uses_base(tmp_path):
    resolved = model_store.resolve_model_path("models/faster-whisper-small", str(tmp_path))
    assert resolved == os.path.normpath(os.path.join(str(tmp_path), "models/faster-whisper-small"))
    assert model_store.resolve_model_path("small", str(tmp_path)) == "small"
    assert model_store.resolve_model_path("", str(tmp_path)) == ""


def test_scan_finds_nested_models_and_stops_descending(tmp_path):
    found = tmp_path / "a" / "model"
    _make_model(found)
    deeper = found / "nested"
    (deeper / "model.bin").parent.mkdir(parents=True, exist_ok=True)
    (deeper / "model.bin").write_bytes(b"x")

    results = model_store.scan_model_dirs(str(tmp_path))
    assert str(found) in results
    assert str(deeper) not in results


def test_human_size_readable():
    assert model_store.human_size(0) == "0 B"
    assert model_store.human_size(1024) == "1.0 KB"
    assert model_store.human_size(1024 * 1024) == "1.0 MB"
