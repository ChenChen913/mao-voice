# facts.md

> README 的唯一事实来源。A 部分由 AI 扫描生成后人工核对；B 部分取自仓库内用户文档（PRD/调研/审核报告），无法溯源的留 TODO。
> 生成日期：2026-09-28

## A. 可自动提取的事实

1. **项目类型**：Windows 桌面 AI 语音输入工具（readme-writer 类型⑩：AI 小项目）
2. **主语言 / 运行时 / 最低版本**：Python；doctor.py 要求 >= 3.10（doctor.py:82），CI 在 3.12 / 3.13 测试（.github/workflows/ci.yml: matrix）
3. **安装命令**：`pip install -r requirements.txt`（来源：部署文档 §5.3、README；requirements.txt 存在，已实跑）
4. **运行命令**：`python main.py`（voice_ime/main.py:485；部署文档 §6.2）或双击 `voice_ime/启动.bat`（部署文档 §6.1）
5. **测试命令**：`python -m pytest voice_ime/tests -q`（ci.yml 同款）→ 实跑结果：**120 passed in 21.54s**（2026-09-28，`py -3.13 -m pytest voice_ime/tests -q`）
6. **构建命令**：`python packaging/build_exe.py`（可选 `--cpu-only`；packaging/build_exe.py docstring）；本机已实跑并冒烟通过
7. **环境自检命令**：`python doctor.py` → 实跑结果 **7/7 全绿**（2026-09-28）
8. **目录结构**（三层内）：
   - `voice_ime/` — 全部运行时代码（16 个 .py 模块，`ls voice_ime/*.py | wc -l` → 16；`wc -l voice_ime/*.py` → 5249 行）
   - `voice_ime/tests/` — pytest 单元测试（120 项）
   - `voice_ime/models/` — 本地模型（gitignore，不入库）
   - `packaging/` — PyInstaller 打包脚本与图标
   - `docs/` — 计划与资料（提示词、审核报告、更新记录）
   - `.github/workflows/` — ci.yml（测试）、package.yml（tag 触发打包发布）
9. **主要依赖**（requirements.txt，9 个）：faster-whisper（>=1.0.0,<1.3，本地转写）、ctranslate2（>=4.0,<5，推理后端）、sounddevice（录音）、pynput（热键与按键模拟）、numpy、requests（LLM/云端 ASR HTTP）、onnxruntime（faster-whisper VAD）、pystray + Pillow（托盘图标）
10. **环境变量**（config.py:107-111，grep `os.environ` 验证）：
    - `DEEPSEEK_API_KEY` — LLM 纠错 API Key 兜底（refine.api_key 为空时读取）
    - `ASR_API_KEY` — 云端 ASR API Key 兜底（其次回退 DEEPSEEK_API_KEY）
11. **模型实测大小**（`du -sh voice_ime/models/*`，2026-09-28）：medium = 1.5G，small = 464M
12. **已有文档**：部署文档.md、PRD_AI语音输入法.md、SPEC_AI语音输入法_MVP.md、AI语音输入法_调研与产品设计.md、项目审核报告.md、深度审核报告_2026-08-04.md、深度审核报告_第二轮_2026-08-04.md、深度审核报告_第三轮_2026-09-28.md、voice_ime/OCR审查报告.md
13. **许可证**：Apache-2.0（LICENSE 文件存在）

## B. 需人工补充（本仓库的溯源结果）

- **一句话描述**（< 120 字符）：源自现行 README 首句 + PRD §1 一句话定位——
  「按一下热键开始录音，再按一下结束：本地 Whisper 识别 + 大模型保守纠错，干净文本直接注入当前输入框的 Windows 工具。」
- **为什么做这个项目**：PRD §1 背景与定位（"说人话、出好文"；识别准/输出净/注入稳/可离线）；调研文档 §竞品分析（现成语音输入工具的输出需手动整理）
- **目标用户 / 前置知识**：PRD 定位为个人用户的 Windows 桌面效率工具（项目审核报告 §1：黑客松/个人工具定位）；使用者无需前置知识，部署需要能执行 PowerShell 命令
- **与同类方案的差异**（调研文档 §7.1 竞品对照 + PRD 价值主张）：
  1. 识别在本地（faster-whisper，GPU 加速，断网可用），仅纠错一步走 LLM
  2. 保守纠错（只修识别错误，不改写原意；三档强度可调）
  3. 安全注入（剪贴板全格式备份恢复、UIPI 预检、序列号冲突检测；v5.18 起终端窗口自动走 Unicode 直注）
  4. 自学习纠错（v5.18：高频纠错对沉淀为规则库拼入提示词，默认关闭）
- **已知限制 / 明确不做的事**（审核报告第一~三轮 + 代码）：
  1. 仅支持 Windows；macOS / 移动端在路线图未实现
  2. 云端 ASR 兜底（cloud_asr.py）代码就绪但从未用真实端点实测（审核报告第三轮 遗留#1）
  3. 管理员权限窗口的注入被 UIPI 拦截（预检提示，文本降级到剪贴板）
  4. 历史记录 / 学习规则为明文落盘（均默认关闭，设置页有明文风险提示）
  5. LLM 纠错需要 DeepSeek 等 OpenAI 兼容 API Key，按量计费；不填 key 时输出原始转写（不产生费用）
- **演示素材路径**：无——v5.9 已删除过期截图（README v5.9 变更记录）；**TODO: 需补充新的运行截图/GIF**（README 按 skill 规则以 Mermaid 流程图代替，未引用不存在的图片）
- **AI 参与声明**：README「开发与维护」节原文——"本项目由总 Agent（编排层）拆解任务、调用实体 Agent 分模块实现后集成"；经 8+ 轮 open-code-review 与三轮深度审核（人工验证）

## 核对记录

- [x] 所有命令实际执行过（pip install / doctor.py / pytest / download_model.py --dry-run / compileall / build_exe.py，2026-09-28）
- [x] 所有环境变量在代码中能搜到（config.py:107-111）
- [x] 目录结构与实际一致（git ls-files）
- [x] 无臆造项（数字均附产生命令；无法验证的数字——如转写耗时——未写入 README）
