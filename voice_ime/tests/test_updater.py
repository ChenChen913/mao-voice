# -*- coding: utf-8 -*-
"""更新检查测试。"""
import updater


def test_parse_version_and_is_newer():
    assert updater.parse_version("v6.0.0") == (6, 0, 0)
    assert updater.parse_version("6.1.2") == (6, 1, 2)
    assert updater.parse_version("nightly") is None
    assert updater.is_newer("5.19.1", "v6.0.0") is True
    assert updater.is_newer("6.0.0", "v6.0.0") is False
    assert updater.is_newer("bad", "v6.0.0") is False


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_check_latest_reports_newer(monkeypatch):
    monkeypatch.setattr(
        updater.requests, "get",
        lambda *a, **k: _Resp(200, {
            "tag_name": "v6.0.0", "html_url": "https://example.com/release",
        }),
    )
    monkeypatch.setattr(updater, "__version__", "5.19.1")
    result = updater.check_latest()
    assert result["ok"] is True
    assert result["latest"] == "v6.0.0"
    assert "发现新版本" in result["message"]
    assert result["url"] == "https://example.com/release"


def test_check_latest_up_to_date_and_network_error(monkeypatch):
    monkeypatch.setattr(
        updater.requests, "get", lambda *a, **k: _Resp(200, {"tag_name": "v5.19.1"})
    )
    monkeypatch.setattr(updater, "__version__", "5.19.1")
    assert "已是最新" in updater.check_latest()["message"]

    def boom(*a, **k):
        raise RuntimeError("offline")

    monkeypatch.setattr(updater.requests, "get", boom)
    result = updater.check_latest()
    assert result["ok"] is False
    assert "检查更新失败" in result["message"]
