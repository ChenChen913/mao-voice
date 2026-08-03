# -*- coding: utf-8 -*-
"""Refiner（DeepSeek 润色）单元测试：mock requests，不联网。"""
import pytest

import refiner


class FakeResp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = "body"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise refiner.requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


def _make_refiner():
    return refiner.Refiner({
        "refine": {"enabled": True, "api_key": "k", "base_url": "https://x/v1",
                   "level": "conservative", "timeout_sec": 5},
    })


def test_prompt_contains_level_and_words(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append((url, json["messages"][0]["content"]))
        return FakeResp(payload={"choices": [{"message": {"content": "结果"}}]})

    monkeypatch.setattr(refiner.requests, "post", fake_post)
    r = _make_refiner()
    out = r.refine("原文", words_block="- 配森 → Python")
    assert out == "结果"
    system = calls[0][1]
    assert "保守修正" in system
    assert "配森 → Python" in system


def test_words_block_braces_do_not_break(monkeypatch):
    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(1)
        return FakeResp(payload={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(refiner.requests, "post", fake_post)
    r = _make_refiner()
    assert r.refine("原文", words_block="x={y}") == "ok"


@pytest.mark.parametrize("content,expected", [
    (["not", "a", "string"], "原文"),
    ("", "原文"),
    ("   ", "原文"),
    ("干净结果", "干净结果"),
])
def test_content_variants(monkeypatch, content, expected):
    monkeypatch.setattr(refiner.requests, "post",
                        lambda *a, **k: FakeResp(payload={"choices": [{"message": {"content": content}}]}))
    r = _make_refiner()
    assert r.refine("原文") == expected


def test_4xx_no_retry(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResp(status=401)

    monkeypatch.setattr(refiner.requests, "post", fake_post)
    r = _make_refiner()
    with pytest.raises(refiner.requests.HTTPError):
        r.refine("原文")
    assert len(calls) == 1


def test_429_retries(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResp(status=429)

    monkeypatch.setattr(refiner.requests, "post", fake_post)
    r = _make_refiner()
    with pytest.raises(refiner.requests.HTTPError):
        r.refine("原文")
    assert len(calls) == refiner.MAX_ATTEMPTS


def test_5xx_retries(monkeypatch):
    calls = []

    def fake_post(*a, **k):
        calls.append(1)
        return FakeResp(status=500)

    monkeypatch.setattr(refiner.requests, "post", fake_post)
    r = _make_refiner()
    with pytest.raises(refiner.requests.HTTPError):
        r.refine("原文")
    assert len(calls) == refiner.MAX_ATTEMPTS
