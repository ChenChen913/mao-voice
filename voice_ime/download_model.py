# -*- coding: utf-8 -*-
"""一键下载 faster-whisper CTranslate2 模型（默认 ModelScope 国内镜像）。

用法：
    python download_model.py                  # 下载默认 medium 到 models/faster-whisper-medium
    python download_model.py --model small    # 可选 small / medium
    python download_model.py --dir my_models  # 自定义模型根目录
    python download_model.py --mirror hf      # 备用镜像 HuggingFace
    python download_model.py --dry-run        # 只打印 URL，不真正下载（测试用）

下载完成后自动把 config.json 的 asr.model 更新为相对路径（如 models/faster-whisper-medium）。
仅依赖 Python 标准库，可在安装项目依赖之前运行。
"""
import argparse
import os
import sys
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIRS = {
    "small": "faster-whisper-small",
    "medium": "faster-whisper-medium",
}
FILES = ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin")

MIRRORS = {
    "modelscope": "https://modelscope.cn/models/Systran/{name}/resolve/master/{file}",
    "hf": "https://huggingface.co/Systran/{name}/resolve/main/{file}",
}


def build_urls(model, mirror="modelscope"):
    """返回 [(远程 URL, 目标相对文件名)] 列表。"""
    name = MODEL_DIRS[model]
    tmpl = MIRRORS[mirror]
    return [(tmpl.format(name=name, file=f), f) for f in FILES]


def human_size(n):
    """字节数转可读大小。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"  # 不可达，兜底


def download_file(url, dest):
    """带进度的下载单个文件；返回字节数。"""
    req = urllib.request.Request(url, headers={"User-Agent": "mao-voice-downloader/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {os.path.basename(dest)}: {human_size(done)}/{human_size(total)} ({pct}%)", end="")
        print()
    return done


def update_config_model(model_dir_name, config_path=None):
    """把 config.json 的 asr.model 更新为相对路径（相对 voice_ime/）。"""
    config_path = config_path or os.path.join(BASE_DIR, "config.json")
    try:
        import config
        cfg = config.load_config(config_path)
        cfg["asr"]["model"] = os.path.join("models", model_dir_name)
        config.save_config(cfg, config_path)
        print(f"[配置] 已更新 {config_path} 的 asr.model -> {cfg['asr']['model']}")
    except Exception as e:
        print(f"[警告] 更新 config.json 失败（可手动编辑）：{e}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="下载 faster-whisper CTranslate2 模型")
    ap.add_argument("--model", choices=sorted(MODEL_DIRS), default="medium")
    ap.add_argument("--dir", default=os.path.join(BASE_DIR, "models"), help="模型根目录")
    ap.add_argument("--mirror", choices=sorted(MIRRORS), default="modelscope")
    ap.add_argument("--dry-run", action="store_true", help="只打印 URL，不下载")
    args = ap.parse_args(argv)

    model_dir_name = MODEL_DIRS[args.model]
    target_dir = os.path.join(args.dir, model_dir_name)
    urls = build_urls(args.model, args.mirror)

    print(f"模型: {args.model}  镜像: {args.mirror}")
    print(f"目标目录: {target_dir}")
    for url, fname in urls:
        print(f"  {fname:16s} <- {url}")
    if args.dry_run:
        print("[dry-run] 不执行下载")
        return

    os.makedirs(target_dir, exist_ok=True)
    for url, fname in urls:
        dest = os.path.join(target_dir, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"[跳过] {fname} 已存在（{human_size(os.path.getsize(dest))}）")
            continue
        part = dest + ".part"  # v5.14：先写 .part，成功后再原子改名，防中断留下残缺文件
        print(f"[下载] {fname} ...")
        try:
            download_file(url, part)
            os.replace(part, dest)
        except KeyboardInterrupt:
            try:
                if os.path.exists(part):
                    os.remove(part)
            except OSError:
                pass
            print("\n已取消")
            sys.exit(130)
        except Exception as e:
            try:
                if os.path.exists(part):
                    os.remove(part)
            except OSError:
                pass
            print(f"[失败] {fname}: {e}")
            sys.exit(1)

    print(f"[完成] 模型已就绪：{target_dir}")
    update_config_model(model_dir_name)


if __name__ == "__main__":
    main()
