# -*- coding: utf-8 -*-
"""诊断信息导出：环境自检 + 配置摘要 + 模型/数据文件位置。

原则：只导出排障所需信息，API Key 只显示是否已配置，绝不写明文；
不包含任何转写文本或历史内容。
"""
import json
import os
import platform
import sys
import time

import doctor
from config import BASE_DIR, CONFIG_PATH, WORDS_PATH, load_config, load_words
from version import __version__


def _masked_config(cfg):
    """提取可公开的配置字段；密钥只保留"已配置/未配置"。"""
    asr = cfg.get("asr") or {}
    refine = cfg.get("refine") or {}
    cloud = asr.get("cloud") or {}
    recorder = cfg.get("recorder") or {}
    inject = cfg.get("inject") or {}
    return {
        "hotkey": cfg.get("hotkey"),
        "settings_hotkey": cfg.get("settings_hotkey"),
        "refine_cycle_hotkey": cfg.get("refine_cycle_hotkey"),
        "asr": {
            "engine": asr.get("engine"),
            "model": asr.get("model"),
            "language": asr.get("language"),
            "cloud_fallback": asr.get("cloud_fallback"),
            "cloud_base_url": cloud.get("base_url"),
            "cloud_api_key": "已配置" if cloud.get("api_key") else "未配置",
        },
        "recorder": {
            "device": recorder.get("device"),
            "max_duration_sec": recorder.get("max_duration_sec"),
            "auto_stop_silence_sec": recorder.get("auto_stop_silence_sec"),
            "warmup_drafts": recorder.get("warmup_drafts"),
        },
        "inject": {
            "paste_mode": inject.get("paste_mode"),
            "restore_delay_sec": inject.get("restore_delay_sec"),
            "require_same_focus": inject.get("require_same_focus"),
        },
        "history_enabled": bool((cfg.get("history") or {}).get("enabled")),
        "learn_enabled": bool((cfg.get("learn") or {}).get("enabled")),
        "refine": {
            "enabled": refine.get("enabled"),
            "level": refine.get("level"),
            "base_url": refine.get("base_url"),
            "api_key": "已配置" if refine.get("api_key") else "未配置",
        },
    }


def collect_report(cfg=None):
    """生成纯文本诊断报告。"""
    cfg = cfg or load_config()
    lines = [
        "mao-voice 诊断报告",
        "生成时间：{}".format(time.strftime("%Y-%m-%d %H:%M:%S")),
        "版本：v{}".format(__version__),
        "Python：{}".format(sys.version.split()[0]),
        "平台：{}".format(platform.platform()),
        "打包运行：{}".format(bool(getattr(sys, "frozen", False))),
        "程序目录：{}".format(BASE_DIR),
        "",
        "== 配置摘要（密钥已脱敏） ==",
        json.dumps(_masked_config(cfg), ensure_ascii=False, indent=2),
        "",
        "== 模型目录 ==",
    ]

    from model_store import cuda_available, human_size, validate_model_dir
    model = (cfg.get("asr") or {}).get("model", "")
    result = validate_model_dir(model)
    lines.append("路径：{}".format(model or "（空）"))
    lines.append("状态：{}".format(result["message"]))
    lines.append("大小：{}".format(result["size_text"]))
    lines.append("CUDA 运行库：{}".format("可用" if cuda_available() else "不可用（CPU 模式）"))

    terms, mappings = load_words()
    lines += [
        "",
        "== 数据文件 ==",
        "词库.txt：{}（热词 {} 条，替换规则 {} 条）".format(
            WORDS_PATH, len(terms), len(mappings)
        ),
        "config.json：{}（{} 字节）".format(CONFIG_PATH, _size_text(CONFIG_PATH)),
        "history.json：{}".format(_size_text(os.path.join(BASE_DIR, "history.json"))),
        "learned_rules.json：{}".format(
            _size_text(os.path.join(BASE_DIR, "learned_rules.json"))
        ),
        "",
        "== 环境自检 ==",
    ]
    for name, ok, detail in doctor.run():
        lines.append("[{}] {}：{}".format("通过" if ok else "失败", name, detail))
    lines.append("")
    return "\n".join(lines)


def _size_text(path):
    try:
        return "{:.1f} KB".format(os.path.getsize(path) / 1024)
    except OSError:
        return "不存在"


def export_report(path, cfg=None):
    """写入诊断报告，返回 (是否成功, 说明)。"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(collect_report(cfg))
        return True, "诊断信息已导出到 {}".format(path)
    except OSError as e:
        return False, "导出失败：{}".format(e)
