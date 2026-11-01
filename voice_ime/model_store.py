# -*- coding: utf-8 -*-
"""模型目录检测与扫描：供设置页和首次向导复用。

只做文件系统层面的检查，不加载模型、不联网，保证在 UI 线程里也能快速返回。
"""
import os

REQUIRED_FILES = ("model.bin", "config.json", "tokenizer.json")
VOCAB_FILES = ("vocabulary.json", "vocabulary.txt")
MAX_SCAN_DIRS = 4000
MAX_SCAN_DEPTH = 3


def human_size(size):
    """字节数转可读大小。"""
    try:
        size = float(size)
    except (TypeError, ValueError):
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return "{:.0f} B".format(size) if unit == "B" else "{:.1f} {}".format(size, unit)
        size /= 1024
    return "—"


def dir_size(path):
    """目录内所有文件字节数之和；读取失败按 0 处理。"""
    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_file():
                    try:
                        total += entry.stat().st_size
                    except OSError:
                        pass
    except OSError:
        return 0
    return total


def resolve_model_path(path, base):
    """相对模型目录按 base 解析（与 config.load_config 的约定一致）。"""
    path = (path or "").strip()
    if not path:
        return ""
    if os.path.isabs(path):
        return path
    if "/" in path or "\\" in path or path.startswith("."):
        return os.path.normpath(os.path.join(base, path))
    return path


def validate_model_dir(path):
    """校验 faster-whisper (CTranslate2) 目录，返回可读结果。

    返回 dict：ok / message / missing / size_bytes / size_text
    """
    path = (path or "").strip()
    if not path:
        return {
            "ok": False, "message": "尚未选择模型目录",
            "missing": [], "size_bytes": 0, "size_text": "—",
        }
    if not os.path.isdir(path):
        return {
            "ok": False, "message": "目录不存在：{}".format(path),
            "missing": [], "size_bytes": 0, "size_text": "—",
        }
    missing = [name for name in REQUIRED_FILES
               if not os.path.isfile(os.path.join(path, name))]
    if not any(os.path.isfile(os.path.join(path, name)) for name in VOCAB_FILES):
        missing.append("vocabulary.json / vocabulary.txt")
    size = dir_size(path)
    if missing:
        return {
            "ok": False,
            "message": "缺少文件：{}".format("、".join(missing)),
            "missing": missing, "size_bytes": size, "size_text": human_size(size),
        }
    return {
        "ok": True,
        "message": "目录有效，可被 faster-whisper 直接加载",
        "missing": [], "size_bytes": size, "size_text": human_size(size),
    }


def scan_model_dirs(root, max_depth=MAX_SCAN_DEPTH, limit=MAX_SCAN_DIRS):
    """在 root 下广度优先查找包含 model.bin 的目录。

    返回绝对路径列表（最多 limit 个目录），不会进入已命中的模型目录继续下探。
    """
    root = (root or "").strip()
    if not root or not os.path.isdir(root):
        return []
    found = []
    visited = 0
    queue = [(os.path.abspath(root), 0)]
    while queue and visited < limit:
        current, depth = queue.pop(0)
        visited += 1
        try:
            with os.scandir(current) as it:
                entries = [e for e in it if e.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        if os.path.isfile(os.path.join(current, "model.bin")):
            found.append(current)
            continue
        if depth >= max_depth:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                continue
            queue.append((entry.path, depth + 1))
    return found


def cuda_available():
    """CUDA 运行库是否就绪（只查 DLL，不加载模型）。"""
    try:
        import asr
        return bool(asr.gpu_ready())
    except Exception:
        return False
