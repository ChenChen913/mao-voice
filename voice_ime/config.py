"""配置与词库管理。"""
import json
import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WORDS_PATH = os.path.join(BASE_DIR, "词库.txt")

DEFAULT_CONFIG = {
    # toggle 模式热键：按一下开始录音，再按一下结束（改用右 Alt 解放双手，无需按住）
    "hotkey": "alt_r",
    "asr": {
        "engine": "whisper",
        # 默认 small（约 460MB）：medium(约 1.5GB) 首次运行才下载，网络慢时长时间无响应；
        # small 下载快、加载快，中文效果可接受
        "model": "small",
        "language": "zh",
        "cloud": {"base_url": "", "api_key": "", "model": "whisper-1"},
    },
    "recorder": {"auto_stop_silence_sec": 0},
    "refine": {
        "enabled": True,
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "level": "conservative",
        "timeout_sec": 30,
    },
    "ui": {"preview_sec": 1.5, "max_chars": 300},
}


def load_config(path=CONFIG_PATH):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                user = json.load(f)
            _deep_merge(cfg, user)
        except Exception as e:
            # 原实现静默回退默认配置：损坏的配置文件会让用户误以为设置仍生效。
            # 至少记日志暴露失败，避免"配置被悄悄重置"无从察觉
            logging.warning("配置文件 %s 读取/解析失败，已回退默认配置：%s", path, e, exc_info=True)
    return cfg


def save_config(cfg, path=CONFIG_PATH):
    """原子写入：先写同目录临时文件，flush + fsync 落盘后再 os.replace 覆盖。

    直接写目标路径在中断（崩溃/断电/磁盘满）时会留下截断的损坏配置，
    下次 load_config 又静默回退默认；先写临时文件可保证目标要么是旧配置要么是新配置。
    os.replace 保证文件名级别的原子性，但若 rename 前内容尚未刷出用户态缓冲，
    断电可能让磁盘上留下零长/截断的临时文件并被原子改名覆盖好配置——
    故 rename 前必须 f.flush() + os.fsync() 让内容先落盘，原子性 + 持久性才完整。

    v5.11：任一步骤失败时清理残留 .tmp 文件后重新抛出，避免陈旧临时文件堆积；
    调用方（如 ensure_defaults）按需捕获。
    """
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def ensure_defaults(path=CONFIG_PATH, words_path=WORDS_PATH):
    if not os.path.exists(path):
        try:
            save_config(DEFAULT_CONFIG, path)
        except Exception:
            # v5.11：写默认配置失败（只读目录/磁盘满等）不应让启动崩溃，
            # 记日志后用内存默认配置继续运行（与 load_config 的容错风格一致）
            logging.warning("无法写入默认配置 %s，本次使用内存默认配置：", path, exc_info=True)
    if not os.path.exists(words_path):
        try:
            with open(words_path, "w", encoding="utf-8") as f:
                f.write("# 用户词库：每行一条。支持 原词=指定写法，或直接写词条\n")
                f.write("# 示例：\n# 配森=Python\n# 喵酱\n")
        except OSError:
            # v5.11：词库文件写失败不阻塞启动，运行时按空词库处理
            logging.warning("无法创建词库文件 %s：", words_path, exc_info=True)


def _deep_merge(base, override):
    for k, v in override.items():
        base_v = base.get(k)
        if isinstance(v, dict) and isinstance(base_v, dict):
            _deep_merge(base_v, v)
        elif isinstance(base_v, dict) and not isinstance(v, dict):
            # 用户给 dict 键传了标量（如 "ui": null、"asr": "gpu"）：
            # 直接覆盖会整棵丢弃默认子树（连同用户没动过的兄弟键）。
            # 跳过并告警，保留默认子树，行为可预期
            logging.warning("配置项 %s 期望对象，收到非对象值 %r，已忽略该项（保留默认配置）", k, v)
        elif isinstance(v, dict) and base_v is not None and not isinstance(base_v, dict):
            # 对称方向：用户给标量键传了对象（如 "ui": {...} 替换默认字符串）。
            # 保持原有"以用户为准"的覆盖行为，但同样告警，让下游感知该键
            # 类型已被改变（与默认配置不一致，下游若期望标量可能不识别）
            logging.warning("配置项 %s 期望标量，收到对象值 %r，已覆盖为对象（类型与默认配置不一致）", k, v)
            base[k] = v
        else:
            base[k] = v


def load_words(path=WORDS_PATH):
    """返回 (terms, mappings)：terms 是词条列表，mappings 是 [(原词, 指定写法)] 元组列表。

    词库是用户可编辑文件，可能被以其他编码（GBK 等）保存或含非法字节：
    读取/解析失败时降级为空词库并记日志（与 load_config 的容错行为一致），
    绝不让词库问题崩溃整个应用。

    注意：`=值`（空原词）与 `原词=`（空写法）两类残缺条目都会被显式忽略，
    避免映射到空字符串（与 asr._load_glossary 行为保持一致）。
    """
    terms, mappings = [], []
    if not os.path.exists(path):
        return terms, mappings
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        mappings.append((k, v))
                else:
                    terms.append(line)
    except (OSError, UnicodeDecodeError):
        logging.warning("词库 %s 读取失败，已按空词库处理：", path, exc_info=True)
    return terms, mappings


def build_words_block(path=WORDS_PATH):
    terms, mappings = load_words(path)
    lines = [f"- {t}" for t in terms]
    lines += [f"- {k} → {v}" for k, v in mappings]
    return "\n".join(lines) if lines else "（无）"
