# -*- coding: utf-8 -*-
"""检查 GitHub Release 是否有新版本（只在用户点击时联网）。"""
import re

import requests

from version import __version__

REPO = "ChenChen913/mao-voice"
LATEST_URL = "https://api.github.com/repos/{}/releases/latest".format(REPO)
RELEASES_URL = "https://github.com/{}/releases".format(REPO)


def parse_version(text):
    """把 'v6.0.0' / '6.0.0' 解析为 (6, 0, 0)；非法返回 None。"""
    match = re.match(r"^[vV]?(\d+)\.(\d+)\.(\d+)$", (text or "").strip())
    if not match:
        return None
    return tuple(int(x) for x in match.groups())


def is_newer(current, latest):
    cur, new = parse_version(current), parse_version(latest)
    if cur is None or new is None:
        return False
    return new > cur


def check_latest(timeout=6):
    """返回 dict：ok / message / latest / url / current。

    网络/接口失败不抛异常，交给界面展示可读原因。
    """
    try:
        resp = requests.get(
            LATEST_URL,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "mao-voice"},
        )
        if resp.status_code == 404:
            return {
                "ok": False, "latest": "", "url": RELEASES_URL,
                "message": "仓库还没有发布 Release",
            }
        if resp.status_code >= 400:
            return {
                "ok": False, "latest": "", "url": RELEASES_URL,
                "message": "检查更新失败：HTTP {}".format(resp.status_code),
            }
        data = resp.json()
        tag = str(data.get("tag_name") or "")
        url = str(data.get("html_url") or RELEASES_URL)
        if is_newer(__version__, tag):
            return {
                "ok": True, "latest": tag, "url": url,
                "message": "发现新版本 {}（当前 v{}）".format(tag, __version__),
            }
        return {
            "ok": True, "latest": tag, "url": url,
            "message": "已是最新版本（v{}）".format(__version__),
        }
    except Exception as e:
        return {
            "ok": False, "latest": "", "url": RELEASES_URL,
            "message": "检查更新失败：{}".format(e),
        }
