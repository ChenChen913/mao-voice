#!/usr/bin/env python3
"""环境自检脚本 —— Windows 桌面 AI 语音输入法项目

用法：
    cd voice_ime/tasks/hermes-doctor
    python doctor.py

每个检查项独立 try/except，单项失败不影响后续检查。
全部通过退出码 0，有失败退出码 1。
"""

import json
import subprocess
import sys
from pathlib import Path

# Windows GBK 控制台兼容：emoji/中文输出强制走 UTF-8，避免 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ── 常见按键名白名单（对照 pynput.keyboard.Key） ──────────────────────────
_VALID_HOTKEY_NAMES: set[str] = {
    # 修饰键
    "ctrl", "ctrl_l", "ctrl_r",
    "alt", "alt_l", "alt_r", "alt_gr",
    "shift", "shift_l", "shift_r",
    "cmd", "cmd_l", "cmd_r",
    "win", "win_l", "win_r",
    # 功能键
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20",
    # 导航
    "up", "down", "left", "right",
    "home", "end", "page_up", "page_down",
    "insert", "delete",
    # 锁定
    "caps_lock", "num_lock", "scroll_lock",
    # 编辑
    "enter", "return",
    "space", "spacebar",
    "tab",
    "backspace",
    "escape", "esc",
    # 数字/字母
    *(chr(c) for c in range(ord("a"), ord("z") + 1)),
    *(str(i) for i in range(10)),
    # 数字键盘
    *(f"num_{i}" for i in range(10)),
    # 媒体
    "media_volume_up", "media_volume_down", "media_volume_mute",
    "media_play_pause", "media_next", "media_previous",
    # 符号
    "`", "-", "=", "[", "]", "\\", ";", "'", ",", ".", "/",
    # 其他
    "print_screen",
}


def _project_root() -> Path:
    """基于 __file__ 定位项目根目录（voice_ime/）。

    本文件位于  voice_ime/tasks/hermes-doctor/doctor.py，
    所以  .parent.parent.parent  == voice_ime/。
    """
    d = Path(__file__).resolve().parent
    for _ in range(6):
        if (d / "main.py").exists():
            return d
        d = d.parent
    return Path(__file__).resolve().parent


# ═══════════════════════════════════════════════════════════════════════════
# 各项检查（每个函数返回 (名称, 通过, 详情)）
# ═══════════════════════════════════════════════════════════════════════════

def _check_python(version_min: tuple[int, ...] = (3, 10)) -> tuple[str, bool, str]:
    """1. Python 版本 >= 3.10"""
    current = sys.version_info[:2]
    passed = current >= version_min
    detail = (
        f"当前 {sys.version.split()[0]}（要求 >= "
        f"{version_min[0]}.{version_min[1]}）"
    )
    return ("Python 版本", passed, detail)


def _check_dependencies() -> tuple[str, bool, str]:
    """2. 关键依赖完整性"""
    modules = ["pynput", "sounddevice", "numpy", "faster_whisper", "requests", "pyperclip"]
    missing: list[str] = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)

    if missing:
        # 部分模块的导入名 ≠ PyPI 包名（如 faster_whisper → faster-whisper）
        _PIP_NAME_MAP: dict[str, str] = {"faster_whisper": "faster-whisper"}
        pip_names = [_PIP_NAME_MAP.get(m, m) for m in missing]
        return (
            "依赖完整性",
            False,
            f"缺少: {', '.join(missing)}；请运行 pip install {' '.join(pip_names)}",
        )
    return ("依赖完整性", True, "6 个关键依赖全部可用")


def _load_config() -> tuple[dict | None, str | None]:
    """加载并解析 config.json。返回 (data, error_reason)。

    统一 config.json 的读取/解析逻辑，避免 _check_config 和 _check_api_key
    各自重复相同的文件存在性检查和 JSON 解析，确保错误信息一致且文件只读一次。
    成功时返回 (data_dict, None)，失败时返回 (None, error_reason)。
    """
    config_path = _project_root() / "config.json"

    if not config_path.is_file():
        return None, f"{config_path} 不存在，请创建配置文件"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as e:
        return None, f"无法读取 {config_path}: {e}"
    except json.JSONDecodeError as e:
        return None, f"{config_path} JSON 解析失败: {e}"

    if not isinstance(data, dict):
        # v5.11：顶层为数组/字符串/布尔时，后续 .get() 会抛 AttributeError
        # 并被 run() 的通用兜底吞掉，掩盖真实原因；这里直接给出可读诊断
        return None, f"{config_path} 顶层应为 JSON 对象，实际为 {type(data).__name__}"

    return data, None


def _check_config() -> tuple[str, bool, str]:
    """3. config.json 存在、可解析、hotkey 字段合法"""
    data, err = _load_config()
    if err:
        return ("配置完整性", False, err)

    hotkey = data.get("hotkey")
    if hotkey is None:
        return ("配置完整性", False, "缺少 hotkey 字段")
    if not isinstance(hotkey, str):
        return ("配置完整性", False, f"hotkey 应为字符串，实际为 {type(hotkey).__name__}")

    hotkey_parts = [k.strip() for k in hotkey.split("+")]
    # 检查空分割（如 "ctrl+ +alt" 或 "ctrl+" 产生空串）
    empty_parts = [i for i, k in enumerate(hotkey_parts) if not k]
    if empty_parts:
        return (
            "配置完整性",
            False,
            f"hotkey='{hotkey}' 包含空键位（索引 {empty_parts}），"
            "可能是连续 '+' 或末尾多余的 '+' 导致",
        )
    if not hotkey.strip():
        return (
            "配置完整性",
            False,
            "hotkey 为空，请在 config.json 中设置有效的热键",
        )
    unknown = [k for k in hotkey_parts if k.lower() not in _VALID_HOTKEY_NAMES]
    if unknown:
        return (
            "配置完整性",
            False,
            f"hotkey='{hotkey}' 包含未知键名: {unknown}",
        )

    return ("配置完整性", True, f"config.json 可解析，hotkey='{hotkey}' 合法")


def _check_api_key() -> tuple[str, bool, str]:
    """4. refine.api_key 是否已配置（不输出 key 明文）"""
    data, err = _load_config()
    if err:
        return ("API Key", False, err)

    refine = data.get("refine")
    if not isinstance(refine, dict):
        return ("API Key", False, "缺少 refine 字段或类型错误（应为对象）")

    api_key = refine.get("api_key", "")
    if isinstance(api_key, str) and api_key.strip():
        return ("API Key", True, "refine.api_key 已配置（值已隐藏）")
    return ("API Key", False, "refine.api_key 为空或未配置，语音识别后处理将不可用")


def _check_dict_file() -> tuple[str, bool, str]:
    """5. 词库.txt 是否存在"""
    dict_path = _project_root() / "词库.txt"
    if dict_path.is_file():
        size = dict_path.stat().st_size
        return ("词库文件", True, f"词库.txt 存在（{size} 字节）")
    return ("词库文件", False, f"{dict_path} 不存在，请在项目根目录放入词库.txt")


def _check_microphone() -> tuple[str, bool, str]:
    """6. 麦克风：sounddevice 枚举输入设备"""
    try:
        import sounddevice as sd  # noqa: F811
    except ImportError:
        return ("麦克风", False, "sounddevice 未安装，无法检测麦克风")

    devices = sd.query_devices()
    inputs = [d for d in devices if d["max_input_channels"] > 0]

    if not inputs:
        return ("麦克风", False, "未检测到任何音频输入设备，请检查麦克风连接")

    names = ", ".join(d["name"] for d in inputs[:3])
    suffix = " ..." if len(inputs) > 3 else ""
    return ("麦克风", True, f"检测到 {len(inputs)} 个输入设备: {names}{suffix}")


def _check_gpu() -> tuple[str, bool, str]:
    """7. GPU/加速：nvidia-smi 是否可用（不依赖 CUDA 库）"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # v5.11：避免 GBK 控制台下解码 nvidia-smi 输出抛异常
            timeout=15,
        )
    except FileNotFoundError:
        return (
            "GPU/加速",
            False,
            "nvidia-smi 未找到；无 NVIDIA 驱动或未加入 PATH。GPU 不可用时会自动回退 CPU",
        )
    except subprocess.TimeoutExpired:
        return (
            "GPU/加速",
            False,
            "nvidia-smi 超时。GPU 不可用时会自动回退 CPU",
        )

    if result.returncode != 0:
        return (
            "GPU/加速",
            False,
            f"nvidia-smi 返回非零（{result.returncode}）。GPU 不可用时会自动回退 CPU",
        )

    gpu_name = result.stdout.strip().split("\n")[0] if result.stdout.strip() else ""
    if not gpu_name:
        return ("GPU/加速", False, "nvidia-smi 返回空输出。GPU 不可用时会自动回退 CPU")
    return ("GPU/加速", True, f"NVIDIA GPU 可用: {gpu_name}")


# ═══════════════════════════════════════════════════════════════════════════
# 公共接口
# ═══════════════════════════════════════════════════════════════════════════

def run() -> list[tuple[str, bool, str]]:
    """返回 [(检查项名称, 是否通过, 详情或修复建议), ...]

    每项独立 try，单项失败不中断。
    """
    checks = [
        _check_python,
        _check_dependencies,
        _check_config,
        _check_api_key,
        _check_dict_file,
        _check_microphone,
        _check_gpu,
    ]

    results: list[tuple[str, bool, str]] = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:
            results.append(
                (check.__name__, False, f"检查异常（不影响其他项）: {exc}")
            )
    return results


def main() -> None:
    """打印 ✅/❌ 清单与总结。

    退出码：全部通过 = 0，有失败 = 1。
    """
    results = run()

    print()
    print("=" * 62)
    print("  🩺  语音输入法 · 环境自检")
    print("=" * 62)
    for name, passed, detail in results:
        icon = "✅" if passed else "❌"
        print(f"  {icon}  {name}")
        print(f"      {detail}")
    print("=" * 62)

    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)

    if failed == 0:
        print(f"  🎉  全部通过！({total}/{total})")
        print()
        sys.exit(0)
    else:
        print(f"  ⚠️  有 {failed}/{total} 项未通过，请参照上方详情修复。")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
