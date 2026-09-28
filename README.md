<h1 align="center">mao-voice · AI 语音输入法</h1>

<p align="center">
  <b>简体中文</b> | <a href="./README_EN.md">English</a>
  <br><br>
  <a href="https://github.com/ChenChen913/mao-voice/actions/workflows/ci.yml"><img src="https://github.com/ChenChen913/mao-voice/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-blue.svg" alt="License: Apache-2.0"></a>
</p>

按一下热键开始录音，再按一下结束：本地 Whisper 识别 + 大模型保守纠错，干净文本直接注入当前输入框的 Windows 工具。

> [!NOTE]
> 本项目由 AI 辅助开发（多 Agent 编排实现，经 8 轮代码审查工具与三轮人工深度审核），主要逻辑经过验证，但**未做完整的边界测试**。已知限制见下文「已知限制」。遇到问题欢迎提 Issue，请理解这是一个实验性项目。

```mermaid
flowchart LR
    A[按热键] --> B[录音<br>迷你波形胶囊]
    B --> A2[再按热键]
    A2 --> C[本地转写<br>faster-whisper]
    C --> D[LLM 保守纠错<br>可选]
    D --> E[注入当前输入框]
```

## 目录

- [为什么做这个项目](#为什么做这个项目)
- [快速开始](#快速开始)
- [用法](#用法)
- [配置](#配置)
- [项目结构](#项目结构)
- [开发](#开发)
- [常见问题](#常见问题)
- [已知限制](#已知限制)
- [如何贡献](#如何贡献)
- [许可证](#许可证)

## 为什么做这个项目

说话比打字快，但现成语音输入工具的输出往往要再手动整理一遍：语气词、标点、谐音错字（如"配森"→Python）。云端听写方案还要把语音上传第三方。

本项目的做法（动机与取舍源自 [PRD](PRD_AI语音输入法.md) 与[调研文档](AI语音输入法_调研与产品设计.md)）：

- **识别在本地**：faster-whisper 离线转写，GPU 加速，断网可用；只有纠错一步走 LLM
- **保守纠错**：只修明显的识别错误（语气词/标点/谐音术语），不改写原意；三档强度可调
- **安全注入**：注入前完整备份剪贴板所有格式并恢复，UIPI 预检，序列号检测外部修改；终端窗口自动改用 Unicode 直注
- **自学习纠错**：可选开启。润色差异中反复出现的"原词→修正"自动沉淀为规则，拼入后续提示词

## 快速开始

前置要求：Windows 10/11、Python 3.10 及以上（CI 在 3.12/3.13 测试）、麦克风；（可选）NVIDIA GPU 与 CUDA 运行库。

```powershell
git clone https://github.com/ChenChen913/mao-voice.git
cd mao-voice/voice_ime
pip install -r requirements.txt
copy config.example.json config.json    # 编辑后填入 DeepSeek API Key
python download_model.py                # 下载模型（medium 约 1.5 GB，本地实测）
python doctor.py                        # 环境自检，全部 ✅ 后运行
python main.py                          # 或双击 启动.bat
```

> 模型从 ModelScope 下载（国内可达），也可用 `--model small`（约 464 MB）。完整部署步骤与 GPU 加速配置见[部署文档](部署文档.md)。

## 用法

1. 打开任意可输入文字的窗口（记事本、聊天框、文档）
2. **按一下热键**（默认右 Alt）开始录音——屏幕底部中央出现迷你波形胶囊，不抢焦点
3. 说完**再按一下热键**结束——依次显示「转写中 → 润色中 → 注入中」，文字直接注入光标处
4. 退出：右键悬浮窗 → 退出，或托盘图标 → 退出

其他操作：`F8` 打开设置窗口（热键/模型/LLM/词库/历史），`F9` 循环切换润色强度，托盘图标随时查看状态。

不想装 Python 环境？`python packaging/build_exe.py` 可打包为免安装的 exe（详见[部署文档 §5.9](部署文档.md)）。

## 配置

配置文件为 `voice_ime/config.json`（首次运行自动生成，原子写入）。常用项：

| 配置 | 必填 | 默认值 | 说明 |
|---------|------|--------|------|
| `refine.api_key` | 否 | 空 | DeepSeek 等 OpenAI 兼容 API Key。**按量计费**；不填则跳过纠错，直接输出原始转写 |
| `hotkey` | 否 | `alt_r` | 录音开关热键，支持 `alt_r`/`ctrl_r`/`f1`~`f12`/`caps_lock` 等 |
| `asr.model` | 否 | `models/faster-whisper-medium` | 本地模型路径 |
| `asr.language` | 否 | `null` | `null` 为自动检测（中英混杂友好），`"zh"` 固定中文 |
| `refine.level` | 否 | `conservative` | 纠错强度：`conservative`/`light`/`polish` |
| `inject.paste_mode` | 否 | `auto` | `auto` 下终端类窗口自动走 Unicode 直注；可强制 `ctrl_v`/`unicode` |
| `history.enabled` / `learn.enabled` | 否 | `false` | 输入历史 / 自学习纠错。两者都**明文落盘**，默认关闭 |

环境变量（config.py:107-111）：`DEEPSEEK_API_KEY`（纠错 Key 兜底）、`ASR_API_KEY`（云端 ASR Key 兜底）。

词库 `voice_ime/词库.txt`：每行一条热词，或 `原词=指定写法`（如 `配森=Python`），自动拼入识别与纠错提示词。

完整配置项说明见[部署文档 §5.4](部署文档.md)。

## 项目结构

```text
mao-voice/
├── voice_ime/            # 运行时代码：16 个 Python 模块，约 5200 行
│   ├── main.py           # 入口：录音状态机 + 管线编排
│   ├── asr.py            # faster-whisper 引擎（GPU 优先，CPU 回退）
│   ├── safe_inject.py    # 剪贴板注入 + Unicode 直注
│   ├── learn.py          # 自学习纠错规则库
│   ├── models/           # 本地模型（不入库）
│   └── tests/            # pytest 单元测试（120 项）
├── packaging/            # PyInstaller 打包脚本与图标
├── docs/                 # 更新记录、计划与资料
└── 部署文档.md            # 完整部署指南
```

## 开发

```powershell
python -m pytest voice_ime/tests -q     # 运行测试（2026-09-28 实测 120 passed）
python -m compileall -q voice_ime       # 语法检查（CI 同款）
python packaging/build_exe.py           # 打包 exe
```

- 推送到 GitHub 自动跑测试 CI（Windows + Python 3.12/3.13）；打 `v*` tag 触发打包并发布 Release
- 多 Agent 编排工具 `voice_ime/orchestrate.py`（`--list`/`--report`/`--noop`）见 README 历史说明与 [tasks.json](voice_ime/tasks.json)
- 审查与修复过程：[OCR审查报告](voice_ime/OCR审查报告.md)、[项目审核报告](项目审核报告.md)、[第三轮深度审核](深度审核报告_第三轮_2026-09-28.md)
- 完整版本历史见[更新记录](docs/更新记录.md)

## 常见问题

**Q：提示"未配置 API Key"？**
A：编辑 `voice_ime/config.json` 填入 `refine.api_key`，或设置 `DEEPSEEK_API_KEY` 环境变量。不填也能用（输出原始转写，不产生费用）。

**Q：转写报"模型加载失败"？**
A：先运行 `python download_model.py` 下载模型，再用 `python doctor.py` 确认模型路径。

**Q：注入失败 / 文字没出现？**
A：目标窗口以管理员权限运行时会被 UIPI 拦截，此时文字已复制到剪贴板，可手动粘贴。往终端（CMD/Git Bash）注入时程序会自动改用 Unicode 直注。

**Q：`python` 不是内部或外部命令？**
A：安装 Python 时未勾选 "Add Python to PATH"，重装并勾选即可。

更多排查项见[部署文档 FAQ](部署文档.md)。

## 已知限制

- 仅支持 Windows；macOS 版在路线图中（见 [docs/提示词.txt](docs/提示词.txt) 的 Swift 方案），未实现
- 云端 ASR 兜底（`cloud_asr.py`）代码就绪，但未用真实云端端点实测过
- 往管理员权限窗口注入会被 UIPI 拦截（有预检提示与剪贴板降级）
- 输入历史与学习规则为明文落盘（均默认关闭，设置页有风险提示）
- 大块音频全程驻留内存：超长单次录音（默认上限 300 秒）内存占用线性增长

## 如何贡献

欢迎提 [Issue](https://github.com/ChenChen913/mao-voice/issues) 反馈问题与场景边界；PR 请先跑通 `python -m pytest voice_ime/tests -q`。这是一个实验性项目，回应可能不及时，请见谅。

## 许可证

[Apache-2.0](LICENSE)
