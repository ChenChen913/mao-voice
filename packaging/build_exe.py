# -*- coding: utf-8 -*-
"""PyInstaller 打包脚本（v5.18）：把语音输入法打成一键运行的 onedir 应用。

用法（在仓库根目录执行）：
    python packaging/build_exe.py               # 完整打包（含本机已装的 CUDA DLL）
    python packaging/build_exe.py --cpu-only    # 不带 CUDA 运行库（体积小 ~1.5GB）

产物：dist/mao-voice/mao-voice.exe（onedir，含 _internal 依赖目录）
- 运行时在 exe 同目录创建/读写 config.json、词库.txt、models/、history.json
  （config.BASE_DIR 在 frozen 下指向 exe 目录）；
- 模型【不打进包】：体积太大且更新频繁。把 models/faster-whisper-* 放到
  exe 同目录的 models/ 下，或用源码环境的 download_model.py 下载后拷贝。
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "voice_ime")
ICON = os.path.join(ROOT, "packaging", "mao_voice.ico")


def find_nvidia_dll_dirs():
    """扫描当前 Python 环境里 nvidia pip 包的 DLL 目录（cublas/cudnn/nvrtc）。"""
    try:
        import importlib.util
    except ImportError:
        return []
    dirs = []
    seen = set()
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError):
            spec = None
        if spec and spec.submodule_search_locations:
            for loc in spec.submodule_search_locations:
                # DLL 就在包目录内的 bin/ 下（如 nvidia/cublas/bin/cublas64_12.dll）；
                # 兼容个别布局把 bin 放在包目录旁的情况
                for cand in (os.path.join(loc, "bin"),
                             os.path.join(loc, "..", "bin")):
                    cand = os.path.abspath(cand)
                    if os.path.isdir(cand) and cand not in seen:
                        seen.add(cand)
                        dirs.append((pkg, cand))
    return dirs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu-only", action="store_true",
                        help="不打包 CUDA 运行库（exe 走 CPU 推理，体积小）")
    args = parser.parse_args()

    import PyInstaller.__main__  # 延迟导入：--help 无需依赖

    args_list = [
        os.path.join(SRC, "main.py"),
        "--noconfirm",
        "--clean",
        "--name", "mao-voice",
        "--icon", ICON,
        # 模块间是同目录平铺导入（from config import ...），把源码目录加进分析路径
        "--paths", SRC,
        # 托盘：pystray 在 Windows 上动态导入平台后端
        "--hidden-import", "pystray._win32",
        # faster-whisper 自带 silero VAD onnx 资产；sounddevice 携带 PortAudio DLL
        "--collect-data", "faster_whisper",
        "--collect-data", "sounddevice",
        "--collect-binaries", "sounddevice",
        "--collect-binaries", "ctranslate2",
        "--collect-binaries", "onnxruntime",
    ]

    if not args.cpu_only:
        for pkg, bin_dir in find_nvidia_dll_dirs():
            for name in sorted(os.listdir(bin_dir)):
                if name.lower().endswith((".dll", ".so")):
                    # 目标布局 nvidia/<库名>/bin/ 与 asr._frozen_nvidia_dirs 的
                    # 查找约定一致；同目录去重（cublas/cudnn 可能共用目录）
                    dest = os.path.join("nvidia", pkg.split(".")[-1], "bin")
                    args_list += ["--add-binary", "{}{}{}".format(
                        os.path.join(bin_dir, name), os.pathsep, dest)]

    PyInstaller.__main__.run(args_list)

    dist_dir = os.path.join(ROOT, "dist", "mao-voice")
    note = os.path.join(dist_dir, "使用说明-打包版.txt")
    with open(note, "w", encoding="utf-8") as f:
        f.write(
            "mao-voice 打包版使用说明\n"
            "========================\n"
            "1. 双击 mao-voice.exe 运行；首次运行会在本目录创建 config.json 与 词库.txt。\n"
            "2. 模型不打在包里：把 models/faster-whisper-medium（或 small）目录拷到本目录的\n"
            "   models/ 下；或在源码环境运行 voice_ime/download_model.py 下载后整体拷贝。\n"
            "   config.json 里 asr.model 默认 models/faster-whisper-medium，与本说明对齐。\n"
            "3. LLM 纠错需在 config.json 填 refine.api_key（或设置 DEEPSEEK_API_KEY 环境变量）；\n"
            "   不填则直接输出原始转写。\n"
            "4. 详细文档见仓库 README.md 与 部署文档.md。\n"
        )
    print("\n打包完成：{}".format(dist_dir))
    if args.cpu_only:
        print("（CPU 版：目标机器无需 CUDA 运行库）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
